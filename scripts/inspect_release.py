"""Inspect one immutable release and emit an append-only source candidate."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from workshop_registry.models import ModuleSource
from workshop_registry.release import InspectedRelease, inspect_release


def candidate_from_release(release: InspectedRelease) -> dict:
    """Build the source-only version record from verified package bytes."""

    manifest = release.package.manifest
    return {
        "version": manifest.version,
        "releaseTag": release.tag,
        "assetName": release.asset_name,
        "assetBytes": release.asset_bytes,
        "sha256": release.sha256,
        "manifestSha256": release.manifest_sha256,
        "workshopApi": manifest.workshop_api.model_dump(
            by_alias=True,
            mode="json",
        ),
        "luminaVersion": manifest.lumina_version.model_dump(
            by_alias=True,
            mode="json",
        ),
        "permissions": [
            permission.model_dump(by_alias=True, mode="json")
            for permission in manifest.permissions
        ],
        "state": "active",
        "revocation": None,
    }


def _write_json_atomic(path: Path, value: dict) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_candidate(
    modules_directory: Path,
    module_id: str,
    candidate: dict,
) -> None:
    """Append one new version without rewriting reviewed history."""

    source_path = modules_directory / f"{module_id}.json"
    if not source_path.is_file():
        raise ValueError(
            "source module must be reviewed before a version can be applied"
        )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise ValueError("source module root must be an object")
    versions = source.get("versions")
    if not isinstance(versions, list):
        raise ValueError("source module versions must be an array")
    if any(
        isinstance(version, dict)
        and version.get("version") == candidate["version"]
        for version in versions
    ):
        raise ValueError("existing version cannot be rewritten")
    source["versions"] = [*versions, candidate]
    ModuleSource.model_validate(source)
    _write_json_atomic(source_path, source)


def main() -> int:
    """Inspect a release, write its candidate, and optionally append it."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--module-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modules", type=Path, default=Path("modules"))
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()

    inspected = inspect_release(
        repository=arguments.repository,
        tag=arguments.tag,
        expected_module_id=arguments.module_id,
    )
    candidate = candidate_from_release(inspected)
    _write_json_atomic(arguments.output, candidate)
    if arguments.apply:
        append_candidate(
            arguments.modules,
            arguments.module_id,
            candidate,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

