from __future__ import annotations

import base64
import json
import stat
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from workshop_registry.signing import (
    SigningError,
    generate_signing_key,
    load_private_key,
    sign_index,
    verify_detached_signature,
)

INDEX_BYTES = (
    b'{"generatedAt":"2026-07-30T00:00:00Z",'
    b'"modules":[],"schemaVersion":1}\n'
)


def test_signature_covers_exact_index_bytes() -> None:
    private_key = Ed25519PrivateKey.generate()
    signature_bytes = sign_index(
        INDEX_BYTES,
        private_key,
        key_id="test-2026-01",
    )

    assert signature_bytes.endswith(b"\n")
    verify_detached_signature(
        INDEX_BYTES,
        signature_bytes,
        {"test-2026-01": private_key.public_key()},
    )
    with pytest.raises(InvalidSignature):
        verify_detached_signature(
            INDEX_BYTES + b" ",
            signature_bytes,
            {"test-2026-01": private_key.public_key()},
        )


def test_signature_metadata_is_closed_and_key_must_be_known() -> None:
    private_key = Ed25519PrivateKey.generate()
    signature = sign_index(
        INDEX_BYTES,
        private_key,
        key_id="test-2026-01",
    )
    value = json.loads(signature)
    value["unexpected"] = True
    malformed = json.dumps(value).encode()

    with pytest.raises(SigningError, match="metadata"):
        verify_detached_signature(
            INDEX_BYTES,
            malformed,
            {"test-2026-01": private_key.public_key()},
        )
    with pytest.raises(SigningError, match="unknown key"):
        verify_detached_signature(INDEX_BYTES, signature, {})


def test_key_generation_writes_private_pem_and_raw_public_record(
    tmp_path: Path,
) -> None:
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.json"

    generate_signing_key(
        key_id="registry-2026-01",
        private_path=private_path,
        public_path=public_path,
    )

    assert private_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    record = json.loads(public_path.read_text(encoding="utf-8"))
    assert set(record) == {"algorithm", "keyId", "publicKey"}
    assert record["algorithm"] == "Ed25519"
    assert record["keyId"] == "registry-2026-01"
    public_bytes = base64.b64decode(
        record["publicKey"].encode("ascii"),
        validate=True,
    )
    assert len(public_bytes) == 32
    assert (
        base64.b64encode(public_bytes).decode("ascii")
        == record["publicKey"]
    )


def test_key_generation_refuses_wrong_id_and_existing_output(
    tmp_path: Path,
) -> None:
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.json"
    with pytest.raises(SigningError, match="key ID"):
        generate_signing_key(
            key_id="wrong-key",
            private_path=private_path,
            public_path=public_path,
        )

    private_path.write_text("keep", encoding="utf-8")
    with pytest.raises(SigningError, match="already exists"):
        generate_signing_key(
            key_id="registry-2026-01",
            private_path=private_path,
            public_path=public_path,
        )
    assert private_path.read_text(encoding="utf-8") == "keep"


def test_malformed_or_non_ed25519_private_pem_is_rejected() -> None:
    with pytest.raises(SigningError, match="private key"):
        load_private_key(b"not a pem")

