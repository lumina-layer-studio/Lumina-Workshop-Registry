"""Check one reviewed base/head source-directory comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.ownership import compare_ownership


def main() -> int:
    """Reject normal-PR ownership transfers and historical rewrites."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--head-dir", type=Path, required=True)
    arguments = parser.parse_args()
    compare_ownership(arguments.base_dir, arguments.head_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

