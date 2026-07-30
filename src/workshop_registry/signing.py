"""Ed25519 key generation, detached signing, and exact-byte verification."""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .canonical import canonical_json_bytes

PRODUCTION_KEY_ID = "registry-2026-01"


class SigningError(ValueError):
    """Signing key or detached signature metadata is invalid."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=False,
    )


class PublicKeyRecord(_StrictModel):
    key_id: str = Field(alias="keyId", min_length=1, max_length=128)
    algorithm: Literal["Ed25519"]
    public_key: str = Field(alias="publicKey", min_length=44, max_length=44)


class SignatureMetadata(_StrictModel):
    algorithm: Literal["Ed25519"]
    key_id: str = Field(alias="keyId", min_length=1, max_length=128)
    signature: str = Field(min_length=88, max_length=88)


def _canonical_base64(value: str, *, expected_bytes: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
        raise SigningError(f"{label} is not canonical base64") from exc
    if (
        len(decoded) != expected_bytes
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        raise SigningError(
            f"{label} must contain exactly {expected_bytes} bytes"
        )
    return decoded


def load_private_key(pem: bytes) -> Ed25519PrivateKey:
    """Load an unencrypted Ed25519 PKCS8 private key."""

    try:
        key = serialization.load_pem_private_key(pem, password=None)
    except (TypeError, ValueError) as exc:
        raise SigningError("Registry private key is invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError("Registry private key must use Ed25519")
    return key


def sign_index(
    index_bytes: bytes,
    private_key: Ed25519PrivateKey,
    *,
    key_id: str,
) -> bytes:
    """Sign exact index bytes and return strict canonical metadata."""

    if not isinstance(private_key, Ed25519PrivateKey):
        raise SigningError("Registry private key must use Ed25519")
    if not key_id or len(key_id) > 128:
        raise SigningError("Registry key ID is invalid")
    signature = private_key.sign(index_bytes)
    metadata = SignatureMetadata.model_validate(
        {
            "algorithm": "Ed25519",
            "keyId": key_id,
            "signature": base64.b64encode(signature).decode("ascii"),
        }
    )
    return canonical_json_bytes(
        metadata.model_dump(by_alias=True, mode="json")
    )


def verify_detached_signature(
    index_bytes: bytes,
    signature_bytes: bytes,
    trusted_keys: Mapping[str, Ed25519PublicKey],
) -> str:
    """Verify a strict detached record against the exact index bytes."""

    try:
        metadata = SignatureMetadata.model_validate_json(signature_bytes)
    except (ValidationError, ValueError) as exc:
        raise SigningError(
            "Registry signature metadata is invalid"
        ) from exc
    public_key = trusted_keys.get(metadata.key_id)
    if public_key is None:
        raise SigningError("Registry signature uses an unknown key")
    if not isinstance(public_key, Ed25519PublicKey):
        raise SigningError("trusted Registry key must use Ed25519")
    signature = _canonical_base64(
        metadata.signature,
        expected_bytes=64,
        label="Registry signature",
    )
    public_key.verify(signature, index_bytes)
    return metadata.key_id


def _write_exclusive(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def generate_signing_key(
    *,
    key_id: str,
    private_path: Path,
    public_path: Path,
) -> None:
    """Create one production key pair without emitting private material."""

    if key_id != PRODUCTION_KEY_ID:
        raise SigningError(
            f"production key ID must be {PRODUCTION_KEY_ID}"
        )
    if private_path.resolve() == public_path.resolve():
        raise SigningError("private and public key paths must differ")
    if private_path.exists() or public_path.exists():
        raise SigningError("signing key output already exists")

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_record = PublicKeyRecord.model_validate(
        {
            "keyId": key_id,
            "algorithm": "Ed25519",
            "publicKey": base64.b64encode(public_bytes).decode("ascii"),
        }
    )

    try:
        _write_exclusive(private_path, private_bytes, mode=0o600)
        _write_exclusive(
            public_path,
            canonical_json_bytes(
                public_record.model_dump(by_alias=True, mode="json")
            ),
            mode=0o644,
        )
    except Exception:
        private_path.unlink(missing_ok=True)
        public_path.unlink(missing_ok=True)
        raise


def load_public_key_record(payload: bytes) -> tuple[str, Ed25519PublicKey]:
    """Parse one strict public record into its trusted key object."""

    try:
        record = PublicKeyRecord.model_validate_json(payload)
    except (ValidationError, ValueError) as exc:
        raise SigningError("Registry public key record is invalid") from exc
    public_bytes = _canonical_base64(
        record.public_key,
        expected_bytes=32,
        label="Registry public key",
    )
    return (
        record.key_id,
        Ed25519PublicKey.from_public_bytes(public_bytes),
    )

