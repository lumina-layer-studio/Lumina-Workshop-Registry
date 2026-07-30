"""Bounded inspection of immutable public GitHub Release assets."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .models import InspectedPackage, validate_semver
from .package import PackageInspectionError, inspect_package

MAX_RELEASE_ASSET_BYTES = 100 * 1024 * 1024
MAX_RELEASE_METADATA_BYTES = 2 * 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 15.0
READ_TIMEOUT_SECONDS = 60.0
TOTAL_DEADLINE_SECONDS = 10 * 60.0
MAX_REDIRECTS = 5
ALLOWED_ASSET_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
    }
)


class ReleaseInspectionError(ValueError):
    """A public GitHub Release failed immutable-asset inspection."""


@dataclass(frozen=True, slots=True)
class DownloadedReleaseAsset:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class InspectedRelease:
    repository: str
    tag: str
    asset_name: str
    download_url: str
    asset_bytes: int
    sha256: str
    manifest_sha256: str
    package: InspectedPackage


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=CONNECT_TIMEOUT_SECONDS,
        read=READ_TIMEOUT_SECONDS,
        write=READ_TIMEOUT_SECONDS,
        pool=CONNECT_TIMEOUT_SECONDS,
    )


def _validate_repository(repository: str) -> tuple[str, str]:
    parsed = urlsplit(repository)
    parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or repository.endswith("/")
        or len(parts) != 2
        or parts[1].endswith(".git")
    ):
        raise ReleaseInspectionError(
            "repository must be an exact public GitHub HTTPS URL"
        )
    return parts[0], parts[1]


def _validate_asset_url(url: str, *, redirected: bool) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_ASSET_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or (not redirected and bool(parsed.query))
    ):
        raise ReleaseInspectionError(
            "release asset redirect host or URL is not allowed"
        )
    return url


def _response_chunks(response: httpx.Response) -> Iterator[bytes]:
    try:
        yield from response.iter_bytes()
    except httpx.TimeoutException as exc:
        raise ReleaseInspectionError(
            "release asset download timed out"
        ) from exc
    except httpx.HTTPError as exc:
        raise ReleaseInspectionError(
            "release asset download failed"
        ) from exc


def _download_with_client(
    url: str,
    destination: Path,
    client: httpx.Client,
) -> DownloadedReleaseAsset:
    if destination.exists():
        raise ReleaseInspectionError("download destination must not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.part-{uuid.uuid4().hex}"
    )
    current_url = _validate_asset_url(url, redirected=False)
    deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    digest = hashlib.sha256()
    received = 0

    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            if time.monotonic() > deadline:
                raise ReleaseInspectionError(
                    "release asset download timed out"
                )
            try:
                request = client.build_request(
                    "GET",
                    current_url,
                    headers={
                        "Accept": "application/octet-stream",
                        "User-Agent": "Lumina-Workshop-Registry/1",
                    },
                )
                response_context = client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                raise ReleaseInspectionError(
                    "release asset download timed out"
                ) from exc
            except httpx.HTTPError as exc:
                raise ReleaseInspectionError(
                    "release asset download failed"
                ) from exc

            with closing(response_context) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    if redirect_count >= MAX_REDIRECTS:
                        raise ReleaseInspectionError(
                            "release asset redirected too many times"
                        )
                    location = response.headers.get("Location")
                    if not location:
                        raise ReleaseInspectionError(
                            "release asset redirect is missing Location"
                        )
                    current_url = _validate_asset_url(
                        urljoin(current_url, location),
                        redirected=True,
                    )
                    continue
                if response.status_code != 200:
                    raise ReleaseInspectionError(
                        "release asset request failed with status "
                        f"{response.status_code}"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared = int(content_length)
                    except ValueError as exc:
                        raise ReleaseInspectionError(
                            "release asset has invalid Content-Length"
                        ) from exc
                    if declared < 0 or declared > MAX_RELEASE_ASSET_BYTES:
                        raise ReleaseInspectionError(
                            "release asset exceeds size limit"
                        )

                with temporary.open("xb") as output:
                    for chunk in _response_chunks(response):
                        if time.monotonic() > deadline:
                            raise ReleaseInspectionError(
                                "release asset download timed out"
                            )
                        received += len(chunk)
                        if received > MAX_RELEASE_ASSET_BYTES:
                            raise ReleaseInspectionError(
                                "release asset exceeds size limit"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                os.replace(temporary, destination)
                return DownloadedReleaseAsset(
                    path=destination,
                    size=received,
                    sha256=digest.hexdigest(),
                )
        raise ReleaseInspectionError(
            "release asset redirected too many times"
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def download_release_asset(
    url: str,
    destination: str | Path,
    *,
    client: httpx.Client | None = None,
) -> DownloadedReleaseAsset:
    """Download one public release asset with strict bounds and cleanup."""

    path = Path(destination)
    if client is not None:
        return _download_with_client(url, path, client)
    try:
        with httpx.Client(timeout=_timeout()) as owned_client:
            return _download_with_client(url, path, owned_client)
    except httpx.TimeoutException as exc:
        path.unlink(missing_ok=True)
        raise ReleaseInspectionError(
            "release asset download timed out"
        ) from exc


def _files_equal(first: Path, second: Path) -> bool:
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            left_chunk = left.read(1024 * 1024)
            right_chunk = right.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _release_metadata(
    client: httpx.Client,
    *,
    owner: str,
    repository_name: str,
    tag: str,
) -> dict:
    url = (
        f"https://api.github.com/repos/{owner}/{repository_name}"
        f"/releases/tags/{tag}"
    )
    try:
        response = client.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Lumina-Workshop-Registry/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise ReleaseInspectionError(
            "GitHub Release metadata request timed out"
        ) from exc
    except httpx.HTTPError as exc:
        raise ReleaseInspectionError(
            "GitHub Release metadata request failed"
        ) from exc
    if response.status_code != 200:
        raise ReleaseInspectionError(
            "GitHub Release metadata request failed with status "
            f"{response.status_code}"
        )
    if len(response.content) > MAX_RELEASE_METADATA_BYTES:
        raise ReleaseInspectionError(
            "GitHub Release metadata exceeds size limit"
        )
    try:
        value = response.json()
    except ValueError as exc:
        raise ReleaseInspectionError(
            "GitHub Release metadata is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ReleaseInspectionError(
            "GitHub Release metadata root must be an object"
        )
    return value


def inspect_release(
    *,
    repository: str,
    tag: str,
    expected_module_id: str,
    expected_permission_names: tuple[str, ...] | None = None,
    client: httpx.Client | None = None,
) -> InspectedRelease:
    """Download twice and statically inspect one exact public release."""

    owner, repository_name = _validate_repository(repository)
    if not tag.startswith("v"):
        raise ReleaseInspectionError("release tag must equal v<version>")
    try:
        version = validate_semver(tag[1:])
    except ValueError as exc:
        raise ReleaseInspectionError(
            "release tag must equal v<version>"
        ) from exc
    expected_asset_name = (
        f"{expected_module_id}-{version}.lumina-workshop"
    )
    download_url = (
        f"{repository}/releases/download/{tag}/{expected_asset_name}"
    )

    def perform(active_client: httpx.Client) -> InspectedRelease:
        metadata = _release_metadata(
            active_client,
            owner=owner,
            repository_name=repository_name,
            tag=tag,
        )
        if metadata.get("tag_name") != tag:
            raise ReleaseInspectionError(
                "GitHub Release tag does not match requested tag"
            )
        if metadata.get("draft") is not False:
            raise ReleaseInspectionError("draft releases are not allowed")
        if metadata.get("prerelease") is not False:
            raise ReleaseInspectionError(
                "prerelease releases are not allowed"
            )
        assets = metadata.get("assets")
        if not isinstance(assets, list):
            raise ReleaseInspectionError(
                "GitHub Release assets must be an array"
            )
        matches = [
            asset
            for asset in assets
            if isinstance(asset, dict)
            and asset.get("name") == expected_asset_name
        ]
        if len(matches) != 1:
            raise ReleaseInspectionError(
                "release must contain exactly one expected module asset"
            )
        if matches[0].get("browser_download_url") != download_url:
            raise ReleaseInspectionError(
                "release asset URL does not match release identity"
            )

        with tempfile.TemporaryDirectory(
            prefix="lumina-registry-release-"
        ) as temporary_directory:
            directory = Path(temporary_directory)
            first = download_release_asset(
                download_url,
                directory / f"first-{expected_asset_name}",
                client=active_client,
            )
            second = download_release_asset(
                download_url,
                directory / f"second-{expected_asset_name}",
                client=active_client,
            )
            if (
                first.size != second.size
                or first.sha256 != second.sha256
                or not _files_equal(first.path, second.path)
            ):
                raise ReleaseInspectionError(
                    "release asset bytes are not stable across two fetches"
                )
            inspection_path = directory / expected_asset_name
            os.replace(first.path, inspection_path)
            try:
                package = inspect_package(inspection_path)
            except PackageInspectionError as exc:
                raise ReleaseInspectionError(
                    f"release package failed static inspection: {exc}"
                ) from exc
            if package.manifest.id != expected_module_id:
                raise ReleaseInspectionError(
                    "release package module ID does not match"
                )
            if package.manifest.version != version:
                raise ReleaseInspectionError(
                    "release package version does not match tag"
                )
            permission_names = tuple(
                permission.name
                for permission in package.manifest.permissions
            )
            if (
                expected_permission_names is not None
                and permission_names != expected_permission_names
            ):
                raise ReleaseInspectionError(
                    "release package permissions do not match review"
                )
            return InspectedRelease(
                repository=repository,
                tag=tag,
                asset_name=expected_asset_name,
                download_url=download_url,
                asset_bytes=first.size,
                sha256=first.sha256,
                manifest_sha256=package.manifest_sha256,
                package=package,
            )

    if client is not None:
        return perform(client)
    with httpx.Client(timeout=_timeout()) as owned_client:
        return perform(owned_client)
