"""Keep the Registry aligned with the host's API 1.2 material import permission."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from scripts.build_registry import build_registry
from tests.test_backend_contract import LOCK, MAIN, backend_manifest, write_package
from tests.test_build_registry import write_source
from tests.test_package import valid_manifest
from workshop_registry.models import ModuleSource, RegistryIndex
from workshop_registry.package import PackageInspectionError, inspect_package
from workshop_registry.release import InspectedRelease
from workshop_registry.signing import sign_index, verify_detached_signature
from workshop_registry.source_update import candidate_from_release

IMPORT_PERMISSION = {
    "name": "material.import",
    "reason": "Import the material selected by the user.",
}


def material_manifest(version: int, minimum: str) -> dict:
    manifest = valid_manifest() if version == 1 else backend_manifest()
    manifest["workshopApi"]["min"] = minimum
    manifest["permissions"] = [dict(IMPORT_PERMISSION)]
    return manifest


@pytest.mark.parametrize("manifest_version", [1, 2])
def test_material_import_package_roundtrips_a_signed_catalog(
    tmp_path: Path, valid_source: dict, manifest_version: int
) -> None:
    manifest = material_manifest(manifest_version, "1.2.0")
    files = (
        {"backend/main.py": MAIN, "backend/pylock.toml": LOCK.encode()}
        if manifest_version == 2 else {}
    )
    path = write_package(tmp_path, manifest, files)
    package = inspect_package(path)
    repository = valid_source["repository"]
    release = InspectedRelease(
        repository=repository,
        tag="v1.0.0",
        asset_name=path.name,
        download_url=f"{repository}/releases/download/v1.0.0/{path.name}",
        asset_bytes=path.stat().st_size,
        sha256=package.archive_sha256,
        manifest_sha256=package.manifest_sha256,
        package=package,
    )
    candidate = candidate_from_release(release)
    assert candidate["permissions"] == [IMPORT_PERMISSION]
    source = {
        **valid_source,
        "moduleId": manifest["id"],
        "publisher": manifest["publisher"],
        "versions": [candidate],
    }
    write_source(tmp_path / "modules", source)
    # Only the network transport is replaced; the ZIP and reviewed bindings are real.
    payload = build_registry(
        tmp_path / "modules",
        generated_at="2026-11-26T00:00:00Z",
        inspector=lambda _source, _version: release,
    )
    index = RegistryIndex.model_validate_json(payload)
    version = index.modules[0].versions[0]
    assert version.workshop_api.minimum == "1.2.0"
    assert json.loads(payload)["modules"][0]["versions"][0]["permissions"] == [
        IMPORT_PERMISSION
    ]
    private = Ed25519PrivateKey.generate()
    signature = sign_index(payload, private, key_id="test-material-import")
    assert verify_detached_signature(
        payload, signature, {"test-material-import": private.public_key()}
    ) == "test-material-import"


@pytest.mark.parametrize("manifest_version", [1, 2])
def test_material_import_package_rejects_older_api(
    tmp_path: Path, manifest_version: int
) -> None:
    manifest = material_manifest(manifest_version, "1.1.0")
    files = (
        {"backend/main.py": MAIN, "backend/pylock.toml": LOCK.encode()}
        if manifest_version == 2 else {}
    )
    with pytest.raises(PackageInspectionError, match=r"material.import.*1.2.0"):
        inspect_package(write_package(tmp_path, manifest, files))


@pytest.mark.parametrize("minimum", ["1.1.0", "1.2.0"])
@pytest.mark.parametrize("catalog", [False, True])
def test_material_import_source_and_catalog_share_the_api_gate(
    valid_source: dict, valid_index: dict, minimum: str, catalog: bool
) -> None:
    value = valid_index if catalog else valid_source
    model = RegistryIndex if catalog else ModuleSource
    module = value["modules"][0] if catalog else value
    version = module["versions"][0]
    version["workshopApi"]["min"] = minimum
    version["permissions"] = [dict(IMPORT_PERMISSION)]
    if minimum == "1.1.0":
        with pytest.raises(ValidationError, match=r"material.import.*1.2.0"):
            model.model_validate(value)
    else:
        parsed = model.model_validate(value)
        assert parsed.model_dump(by_alias=True, mode="json")["schemaVersion"] == 1


@pytest.mark.parametrize("manifest_version", [1, 2])
def test_existing_permissions_keep_their_original_api_minimum(
    tmp_path: Path, manifest_version: int
) -> None:
    manifest = valid_manifest() if manifest_version == 1 else backend_manifest()
    manifest["permissions"] = [
        {"name": name, "reason": "Existing permission."}
        for name in (
            "image.pick", "project.storage", "color-library.read", "handoff.image"
        )
    ]
    files = (
        {"backend/main.py": MAIN, "backend/pylock.toml": LOCK.encode()}
        if manifest_version == 2 else {}
    )
    package = inspect_package(write_package(tmp_path, manifest, files))
    assert package.manifest.workshop_api.minimum == (
        "1.0.0" if manifest_version == 1 else "1.1.0"
    )
