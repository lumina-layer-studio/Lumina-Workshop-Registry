"""Generate checked JSON Schemas from the strict Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path

from workshop_registry.models import ModuleSource, RegistryIndex

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "module-source-v1.schema.json": ModuleSource,
    "registry-v1.schema.json": RegistryIndex,
}


def main() -> int:
    """Write deterministic model schemas into the reviewed schema directory."""

    output_directory = ROOT / "schemas"
    output_directory.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        payload = (
            json.dumps(
                model.model_json_schema(by_alias=True),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (output_directory / filename).write_text(
            payload,
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

