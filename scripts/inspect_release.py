"""Inspect one immutable release and emit an append-only source candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.release import inspect_release
from workshop_registry.source_update import (
    append_candidate,
    candidate_from_release,
    write_json_atomic,
)


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
    write_json_atomic(arguments.output, candidate)
    if arguments.apply:
        append_candidate(
            arguments.modules,
            arguments.module_id,
            candidate,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
