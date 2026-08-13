"""Append newly published stable module Releases for human review."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from workshop_registry.models import (
    ModuleSource,
    compare_semver,
    semver_sort_key,
    validate_semver,
)
from workshop_registry.release import inspect_release
from workshop_registry.source_update import (
    append_candidate,
    candidate_from_release,
)


def _stable_release_tags(
    source: ModuleSource,
    *,
    client: httpx.Client,
) -> tuple[str, ...]:
    path_parts = tuple(
        part for part in urlsplit(source.repository).path.split("/") if part
    )
    response = client.get(
        (
            f"https://api.github.com/repos/{path_parts[0]}/"
            f"{path_parts[1]}/releases"
        ),
        params={"per_page": 100},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("GitHub releases response must be an array")

    existing = {version.version for version in source.versions}
    candidates: list[str] = []
    for release in payload:
        if (
            not isinstance(release, dict)
            or release.get("draft") is not False
            or release.get("prerelease") is not False
        ):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag.startswith("v"):
            continue
        try:
            version = validate_semver(tag[1:])
        except ValueError:
            continue
        # Automated discovery only handles unambiguous stable releases.
        # Pre-release and build-qualified versions require explicit review.
        if "-" in version or "+" in version:
            continue
        if version not in existing:
            candidates.append(version)
    candidates.sort(key=semver_sort_key)
    return tuple(f"v{version}" for version in candidates)


def scan(modules_directory: Path) -> int:
    """Inspect and append every stable version not already registered."""

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Lumina-Workshop-Registry-Scanner/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    appended = 0
    with httpx.Client(
        timeout=httpx.Timeout(60.0, connect=15.0),
        headers=headers,
    ) as api_client:
        for path in sorted(modules_directory.glob("*.json")):
            source = ModuleSource.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            previous_version = (
                source.versions[-1].version if source.versions else None
            )
            for tag in _stable_release_tags(source, client=api_client):
                if (
                    previous_version is not None
                    and compare_semver(tag[1:], previous_version) <= 0
                ):
                    continue
                inspected = inspect_release(
                    repository=source.repository,
                    tag=tag,
                    expected_module_id=source.module_id,
                )
                append_candidate(
                    modules_directory,
                    source.module_id,
                    candidate_from_release(inspected),
                )
                previous_version = tag[1:]
                appended += 1
    return appended


def main() -> int:
    """Scan reviewed repositories and modify only append-only source records."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--modules", type=Path, default=Path("modules"))
    arguments = parser.parse_args()
    scan(arguments.modules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
