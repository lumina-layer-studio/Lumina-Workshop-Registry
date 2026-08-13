"""Verify exact Registry index bytes with one reviewed public-key record."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.signing import (
    load_public_key_record,
    verify_detached_signature,
)


def main() -> int:
    """Verify the detached signature and trusted key ID."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    arguments = parser.parse_args()
    key_id, public_key = load_public_key_record(
        arguments.public_key.read_bytes()
    )
    verified_id = verify_detached_signature(
        arguments.index.read_bytes(),
        arguments.signature.read_bytes(),
        {key_id: public_key},
    )
    if verified_id != key_id:
        raise RuntimeError("Registry signature key ID changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

