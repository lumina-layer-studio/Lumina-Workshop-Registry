"""Validate every reviewed module source record without network access."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.models import ModuleSource


def validate_source_directory(directory: Path) -> tuple[ModuleSource, ...]:
    """Load closed-schema source records and reject duplicate identities."""

    modules: list[ModuleSource] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        module = ModuleSource.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if path.name != f"{module.module_id}.json":
            raise ValueError(
                f"source filename must equal {module.module_id}.json"
            )
        if module.module_id in seen_ids:
            raise ValueError(f"duplicate module id: {module.module_id}")
        seen_ids.add(module.module_id)
        modules.append(module)
    return tuple(modules)


def main() -> int:
    """Validate the requested source directory."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modules",
        type=Path,
        default=Path("modules"),
    )
    arguments = parser.parse_args()
    validate_source_directory(arguments.modules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

