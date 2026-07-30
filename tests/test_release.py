from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest
import respx

from workshop_registry.release import (
    ReleaseInspectionError,
    download_release_asset,
    inspect_release,
)

from .test_package import required_files, valid_manifest

REPOSITORY = "https://github.com/example/fixture-hello"
API_URL = "https://api.github.com/repos/example/fixture-hello/releases/tags/v1.0.0"
ASSET_NAME = "fixture.hello-1.0.0.lumina-workshop"
ASSET_URL = (
    f"{REPOSITORY}/releases/download/v1.0.0/{ASSET_NAME}"
)


def package_bytes(
    tmp_path: Path,
    *,
    module_id: str = "fixture.hello",
    version: str = "1.0.0",
    permissions: list[dict] | None = None,
) -> bytes:
    manifest = valid_manifest()
    manifest["id"] = module_id
    manifest["version"] = version
    if permissions is not None:
        manifest["permissions"] = permissions
    archive = tmp_path / ASSET_NAME
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        for name, value in required_files().items():
            package.writestr(name, value)
    return archive.read_bytes()


def release_response(
    *,
    draft: bool = False,
    prerelease: bool = False,
    assets: list[dict] | None = None,
) -> dict:
    return {
        "tag_name": "v1.0.0",
        "draft": draft,
        "prerelease": prerelease,
        "assets": (
            [
                {
                    "name": ASSET_NAME,
                    "size": 123,
                    "browser_download_url": ASSET_URL,
                }
            ]
            if assets is None
            else assets
        ),
    }


@respx.mock
def test_release_inspection_pins_actual_bytes(tmp_path: Path) -> None:
    payload = package_bytes(tmp_path)
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=release_response())
    )
    respx.get(ASSET_URL).mock(
        side_effect=[
            httpx.Response(200, content=payload),
            httpx.Response(200, content=payload),
        ]
    )

    inspected = inspect_release(
        repository=REPOSITORY,
        tag="v1.0.0",
        expected_module_id="fixture.hello",
    )

    assert inspected.asset_bytes == len(payload)
    assert inspected.sha256 == hashlib.sha256(payload).hexdigest()
    assert inspected.manifest_sha256 == inspected.package.manifest_sha256
    assert inspected.package.manifest.name.en_us == "Fixture module"


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("draft", "draft"),
        ("prerelease", "prerelease"),
    ],
)
@respx.mock
def test_draft_and_prerelease_are_rejected(
    field: str,
    message: str,
) -> None:
    response = release_response(**{field: True})
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=response))

    with pytest.raises(ReleaseInspectionError, match=message):
        inspect_release(
            repository=REPOSITORY,
            tag="v1.0.0",
            expected_module_id="fixture.hello",
        )


@respx.mock
def test_missing_and_duplicate_assets_are_rejected() -> None:
    for assets in (
        [],
        [
            {
                "name": ASSET_NAME,
                "size": 1,
                "browser_download_url": ASSET_URL,
            },
            {
                "name": ASSET_NAME,
                "size": 1,
                "browser_download_url": ASSET_URL,
            },
        ],
    ):
        respx.get(API_URL).mock(
            return_value=httpx.Response(
                200,
                json=release_response(assets=assets),
            )
        )
        with pytest.raises(ReleaseInspectionError, match="exactly one"):
            inspect_release(
                repository=REPOSITORY,
                tag="v1.0.0",
                expected_module_id="fixture.hello",
            )
        respx.reset()


@respx.mock
def test_redirect_outside_github_asset_hosts_is_rejected(
    tmp_path: Path,
) -> None:
    destination = tmp_path / ASSET_NAME
    respx.get(ASSET_URL).mock(
        return_value=httpx.Response(
            302,
            headers={"Location": "https://evil.example/payload"},
        )
    )

    with pytest.raises(ReleaseInspectionError, match="redirect host"):
        download_release_asset(ASSET_URL, destination)
    assert not destination.exists()


@respx.mock
def test_stream_limit_deletes_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workshop_registry import release

    destination = tmp_path / ASSET_NAME
    monkeypatch.setattr(release, "MAX_RELEASE_ASSET_BYTES", 8)
    respx.get(ASSET_URL).mock(
        return_value=httpx.Response(200, content=b"x" * 9)
    )

    with pytest.raises(ReleaseInspectionError, match="size limit"):
        download_release_asset(ASSET_URL, destination)
    assert not destination.exists()


@respx.mock
def test_second_fetch_must_have_identical_bytes(tmp_path: Path) -> None:
    payload = package_bytes(tmp_path)
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=release_response())
    )
    respx.get(ASSET_URL).mock(
        side_effect=[
            httpx.Response(200, content=payload),
            httpx.Response(200, content=payload + b"changed"),
        ]
    )

    with pytest.raises(ReleaseInspectionError, match="stable"):
        inspect_release(
            repository=REPOSITORY,
            tag="v1.0.0",
            expected_module_id="fixture.hello",
        )


@pytest.mark.parametrize(
    ("module_id", "version", "message"),
    [
        ("other.module", "1.0.0", "module ID"),
        ("fixture.hello", "1.0.1", "version"),
    ],
)
@respx.mock
def test_manifest_identity_must_match_release(
    tmp_path: Path,
    module_id: str,
    version: str,
    message: str,
) -> None:
    payload = package_bytes(
        tmp_path,
        module_id=module_id,
        version=version,
    )
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=release_response())
    )
    respx.get(ASSET_URL).mock(
        side_effect=[
            httpx.Response(200, content=payload),
            httpx.Response(200, content=payload),
        ]
    )

    with pytest.raises(ReleaseInspectionError, match=message):
        inspect_release(
            repository=REPOSITORY,
            tag="v1.0.0",
            expected_module_id="fixture.hello",
        )


@respx.mock
def test_reviewed_permissions_must_match_manifest(
    tmp_path: Path,
) -> None:
    payload = package_bytes(tmp_path)
    respx.get(API_URL).mock(
        return_value=httpx.Response(200, json=release_response())
    )
    respx.get(ASSET_URL).mock(
        side_effect=[
            httpx.Response(200, content=payload),
            httpx.Response(200, content=payload),
        ]
    )

    with pytest.raises(ReleaseInspectionError, match="permissions"):
        inspect_release(
            repository=REPOSITORY,
            tag="v1.0.0",
            expected_module_id="fixture.hello",
            expected_permission_names=("image.pick",),
        )


@respx.mock
def test_network_timeout_is_fail_closed(tmp_path: Path) -> None:
    destination = tmp_path / ASSET_NAME
    respx.get(ASSET_URL).mock(side_effect=httpx.ReadTimeout("stalled"))
    with pytest.raises(ReleaseInspectionError, match="timed out"):
        download_release_asset(ASSET_URL, destination)
    assert not destination.exists()

