"""Canonicalize one JSON document for Registry review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from workshop_registry.canonical import canonical_json_bytes


def main() -> int:
    """Read JSON and write the canonical Registry representation."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    value = json.loads(arguments.input.read_text(encoding="utf-8"))
    arguments.output.write_bytes(canonical_json_bytes(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

