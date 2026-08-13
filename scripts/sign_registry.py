"""Sign exact Registry bytes with a secret PEM supplied only by environment."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from workshop_registry.signing import (
    PRODUCTION_KEY_ID,
    load_private_key,
    sign_index,
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
    """Read the key from one secret variable and write detached metadata."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-id", default=PRODUCTION_KEY_ID)
    arguments = parser.parse_args()
    pem = os.environ.get("REGISTRY_ED25519_PRIVATE_KEY")
    if pem is None:
        raise RuntimeError(
            "REGISTRY_ED25519_PRIVATE_KEY is required"
        )
    signature = sign_index(
        arguments.index.read_bytes(),
        load_private_key(pem.encode("utf-8")),
        key_id=arguments.key_id,
    )
    _write_atomic(arguments.output, signature)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

