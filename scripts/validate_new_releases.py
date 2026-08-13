"""Re-download and validate every version newly appended by a source PR."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.models import ModuleSource, SourceVersion
from workshop_registry.release import inspect_release


def _load(directory: Path) -> dict[str, ModuleSource]:
    return {
        source.module_id: source
        for source in (
            ModuleSource.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            for path in sorted(directory.glob("*.json"))
        )
    }


def _assert_exact(
    source: ModuleSource,
    reviewed: SourceVersion,
) -> None:
    release = inspect_release(
        repository=source.repository,
        tag=reviewed.release_tag,
        expected_module_id=source.module_id,
        expected_permission_names=tuple(
            permission.name for permission in reviewed.permissions
        ),
    )
    manifest = release.package.manifest
    if not (
        release.asset_name == reviewed.asset_name
        and release.asset_bytes == reviewed.asset_bytes
        and release.sha256 == reviewed.sha256
        and release.manifest_sha256 == reviewed.manifest_sha256
        and manifest.publisher == source.publisher
        and manifest.workshop_api == reviewed.workshop_api
        and manifest.lumina_version == reviewed.lumina_version
        and manifest.permissions == reviewed.permissions
    ):
        raise ValueError(
            f"{source.module_id}@{reviewed.version} does not match "
            "its reviewed GitHub Release"
        )


def validate_new_releases(
    base_directory: Path,
    head_directory: Path,
) -> None:
    """Inspect all appended versions while leaving existing history alone."""

    base = _load(base_directory)
    head = _load(head_directory)
    for module_id, source in sorted(head.items()):
        previous_count = (
            len(base[module_id].versions) if module_id in base else 0
        )
        for version in source.versions[previous_count:]:
            _assert_exact(source, version)


def main() -> int:
    """Validate all new versions between explicit base and head directories."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--head-dir", type=Path, required=True)
    arguments = parser.parse_args()
    validate_new_releases(arguments.base_dir, arguments.head_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
