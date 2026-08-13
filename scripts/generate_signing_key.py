"""Generate the production Registry signing key pair at explicit paths."""

from __future__ import annotations

import argparse
from pathlib import Path

from workshop_registry.signing import (
    PRODUCTION_KEY_ID,
    generate_signing_key,
)


def main() -> int:
    """Generate a private PEM and public JSON record without printing them."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--key-id", default=PRODUCTION_KEY_ID)
    parser.add_argument("--private-out", type=Path, required=True)
    parser.add_argument("--public-out", type=Path, required=True)
    arguments = parser.parse_args()
    generate_signing_key(
        key_id=arguments.key_id,
        private_path=arguments.private_out,
        public_path=arguments.public_out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

