from __future__ import annotations

import base64
import errno
import io
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from workshop_registry import signing
from workshop_registry.signing import (
    PRODUCTION_KEY_ID,
    SigningError,
    generate_signing_key,
    load_private_key,
    load_public_key_record,
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

    private_bytes = private_path.read_bytes()
    assert private_bytes.startswith(b"-----BEGIN PRIVATE KEY-----")
    if os.name == "nt":
        assert_private_windows_acl(private_path)
    else:
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
    derived_key = load_private_key(private_bytes).public_key()
    assert derived_key.public_bytes_raw() == public_bytes
    assert (
        base64.b64encode(public_bytes).decode("ascii")
        == record["publicKey"]
    )


def assert_private_windows_acl(private_path: Path) -> None:
    command = """
$ErrorActionPreference = 'Stop'
$acl = [IO.File]::GetAccessControl($env:LUMINA_REGISTRY_TEST_KEY)
$user = [Security.Principal.WindowsIdentity]::GetCurrent().User
$sidType = [Security.Principal.SecurityIdentifier]
$rules = @($acl.GetAccessRules($true, $true, $sidType))
if (-not $acl.AreAccessRulesProtected -or $acl.GetOwner($sidType) -ne $user -or
    $rules.Count -ne 1 -or $rules[0].IsInherited -or
    $rules[0].IdentityReference -ne $user -or $rules[0].AccessControlType -ne 'Allow') {
    throw 'Signing key ACL must allow only the current user'
}
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "LUMINA_REGISTRY_TEST_KEY": str(private_path)},
        check=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.parametrize("competing_name", ["private.pem", "public.json"])
def test_key_generation_preserves_competing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, competing_name: str
) -> None:
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.json"
    competing_path = tmp_path / competing_name
    write_exclusive = signing._write_exclusive

    def write_with_competing_output(path: Path, payload: bytes, *, mode: int) -> None:
        if path == competing_path:
            path.write_bytes(b"another writer")
        write_exclusive(path, payload, mode=mode)

    monkeypatch.setattr(signing, "_write_exclusive", write_with_competing_output)
    with pytest.raises(FileExistsError):
        generate_signing_key(
            key_id=PRODUCTION_KEY_ID,
            private_path=private_path,
            public_path=public_path,
        )

    assert list(tmp_path.iterdir()) == [competing_path]
    assert competing_path.read_bytes() == b"another writer"


@pytest.mark.parametrize(
    ("failing_stream", "error_type"), [(1, OSError), (2, KeyboardInterrupt)]
)
def test_key_generation_rolls_back_if_opening_an_output_stream_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_stream: int,
    error_type: type[BaseException],
) -> None:
    fdopen = os.fdopen
    open_attempts = 0
    failed_descriptor = -1

    def open_output(descriptor: int, mode: str, *, closefd: bool) -> io.BufferedWriter:
        nonlocal open_attempts, failed_descriptor
        open_attempts += 1
        if open_attempts == failing_stream:
            failed_descriptor = descriptor
            raise error_type("could not open the output stream")
        return fdopen(descriptor, mode, closefd=closefd)

    with monkeypatch.context() as patch:
        patch.setattr(signing.os, "fdopen", open_output)
        with pytest.raises(error_type, match="could not open the output stream"):
            generate_signing_key(
                key_id=PRODUCTION_KEY_ID,
                private_path=tmp_path / "private.pem",
                public_path=tmp_path / "public.json",
            )

    assert list(tmp_path.iterdir()) == []
    assert failed_descriptor >= 0
    with pytest.raises(OSError) as closed:
        os.fstat(failed_descriptor)
    assert closed.value.errno == errno.EBADF


@pytest.mark.skipif(os.name != "nt", reason="requires Windows file permissions")
def test_windows_key_generation_requires_persistent_acls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workshop_registry import _windows_private_file

    monkeypatch.setattr(
        _windows_private_file, "_supports_persistent_acls", lambda _: False
    )
    with pytest.raises(OSError, match="requires persistent ACLs"):
        generate_signing_key(
            key_id=PRODUCTION_KEY_ID,
            private_path=tmp_path / "private.pem",
            public_path=tmp_path / "public.json",
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="requires Windows file permissions")
def test_windows_key_generation_refuses_an_inherited_acl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workshop_registry import _windows_private_file

    create_file = _windows_private_file._kernel32.CreateFileW

    def create_with_default_acl(
        path: str, access: int, sharing: int, _security: object, *options: object
    ) -> int:
        return create_file(path, access, sharing, None, *options)

    monkeypatch.setattr(
        _windows_private_file._kernel32, "CreateFileW", create_with_default_acl
    )
    with pytest.raises(PermissionError, match="owner-only ACL"):
        generate_signing_key(
            key_id=PRODUCTION_KEY_ID,
            private_path=tmp_path / "private.pem",
            public_path=tmp_path / "public.json",
        )

    assert list(tmp_path.iterdir()) == []


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


def test_committed_production_public_key_is_strict_and_loadable() -> None:
    key_id, _public_key = load_public_key_record(
        Path("keys/registry-2026-01.public.json").read_bytes()
    )

    assert key_id == PRODUCTION_KEY_ID
