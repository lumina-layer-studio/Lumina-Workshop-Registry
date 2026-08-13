"""Build deterministic Registry index bytes from reviewed source records."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from workshop_registry.canonical import canonical_json_bytes
from workshop_registry.models import (
    ModuleSource,
    RegistryIndex,
    SourceVersion,
)
from workshop_registry.release import InspectedRelease, inspect_release


class RegistryBuildError(ValueError):
    """Reviewed Registry input cannot produce a trusted deterministic index."""


ReleaseInspector = Callable[
    [ModuleSource, SourceVersion],
    InspectedRelease | Any,
]


def _load_sources(directory: Path) -> tuple[ModuleSource, ...]:
    modules: list[ModuleSource] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        source = ModuleSource.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if path.name != f"{source.module_id}.json":
            raise RegistryBuildError(
                f"source filename must equal {source.module_id}.json"
            )
        if source.module_id in seen_ids:
            raise RegistryBuildError(
                f"duplicate module id: {source.module_id}"
            )
        seen_ids.add(source.module_id)
        modules.append(source)
    return tuple(sorted(modules, key=lambda module: module.module_id))


def _live_inspector(
    source: ModuleSource,
    version: SourceVersion,
) -> InspectedRelease:
    return inspect_release(
        repository=source.repository,
        tag=version.release_tag,
        expected_module_id=source.module_id,
        expected_permission_names=tuple(
            permission.name for permission in version.permissions
        ),
    )


def _reject_synthetic_hash(value: str, *, label: str) -> None:
    if len(set(value)) == 1:
        raise RegistryBuildError(f"{label} is a synthetic hash")


def _assert_review_matches_release(
    source: ModuleSource,
    reviewed: SourceVersion,
    release: Any,
) -> None:
    manifest = release.package.manifest
    exact_values_match = (
        release.asset_name == reviewed.asset_name
        and release.asset_bytes == reviewed.asset_bytes
        and release.sha256 == reviewed.sha256
        and release.manifest_sha256 == reviewed.manifest_sha256
        and release.package.manifest_sha256 == reviewed.manifest_sha256
        and manifest.id == source.module_id
        and manifest.version == reviewed.version
        and manifest.publisher == source.publisher
        and manifest.workshop_api == reviewed.workshop_api
        and manifest.lumina_version == reviewed.lumina_version
        and manifest.permissions == reviewed.permissions
    )
    if not exact_values_match:
        raise RegistryBuildError(
            f"{source.module_id}@{reviewed.version} reviewed bytes "
            "or manifest contract do not match the Release"
        )


def _normalize_generated_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegistryBuildError("generatedAt must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RegistryBuildError("generatedAt must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def build_registry(
    source_directory: Path,
    *,
    generated_at: str,
    inspector: ReleaseInspector | None = None,
) -> bytes:
    """Build exact canonical index bytes after re-inspecting every release."""

    inspect_one = inspector or _live_inspector
    output_modules: list[dict[str, Any]] = []
    for source in _load_sources(source_directory):
        output_versions: list[dict[str, Any]] = []
        display_name: dict[str, str] | None = None
        description: dict[str, str] | None = None
        for reviewed in source.versions:
            _reject_synthetic_hash(
                reviewed.sha256,
                label=f"{source.module_id}@{reviewed.version} sha256",
            )
            _reject_synthetic_hash(
                reviewed.manifest_sha256,
                label=(
                    f"{source.module_id}@{reviewed.version} manifestSha256"
                ),
            )
            release = inspect_one(source, reviewed)
            _assert_review_matches_release(source, reviewed, release)
            manifest = release.package.manifest
            current_name = manifest.name.model_dump(
                by_alias=True,
                mode="json",
            )
            current_description = manifest.description.model_dump(
                by_alias=True,
                mode="json",
            )
            if display_name is None:
                display_name = current_name
                description = current_description
            elif (
                current_name != display_name
                or current_description != description
            ):
                raise RegistryBuildError(
                    f"{source.module_id} localized display metadata "
                    "must be stable across registered versions"
                )
            version_value = reviewed.model_dump(
                by_alias=True,
                mode="json",
            )
            version_value["downloadUrl"] = release.download_url
            output_versions.append(version_value)

        if not output_versions or display_name is None or description is None:
            continue
        output_modules.append(
            {
                "moduleId": source.module_id,
                "repository": source.repository,
                "official": source.official,
                "publisher": source.publisher,
                "name": display_name,
                "description": description,
                "versions": output_versions,
            }
        )

    raw_index = {
        "schemaVersion": 1,
        "generatedAt": _normalize_generated_at(generated_at),
        "modules": output_modules,
    }
    index = RegistryIndex.model_validate(raw_index)
    return canonical_json_bytes(
        index.model_dump(by_alias=True, mode="json")
    )


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    """Build and atomically write one reviewed unsigned Registry index."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--modules", type=Path, default=Path("modules"))
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    payload = build_registry(
        arguments.modules,
        generated_at=arguments.generated_at,
    )
    _write_atomic(arguments.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

