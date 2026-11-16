"""Manifest v2 packages and signed backend review attestations."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from scripts.build_pages import build_pages
from scripts.build_registry import (
    RegistryBuildError,
    build_registry,
    build_registry_outputs,
)
from tests.test_build_registry import release_for, write_source
from tests.test_package import PNG_1X1
from workshop_registry.models import (
    ModuleSource,
    RegistryIndex,
    ReviewIndex,
    WorkshopManifestV2,
)
from workshop_registry.package import PackageInspectionError, inspect_package

GENERATED_AT = "2026-11-04T00:00:00Z"
WHEEL_URL = "https://files.pythonhosted.org/packages/aa/demo-1.0.0-py3-none-any.whl"
LOCK = (
    'lock-version = "1.0"\n'
    "[[packages]]\n"
    'name = "demo"\n'
    'version = "1.0.0"\n'
    "[[packages.wheels]]\n"
    f'url = "{WHEEL_URL}"\n'
    f'hashes = {{ sha256 = "{"c" * 64}" }}\n'
)
MAIN = b"x = 1\n"


def backend_manifest() -> dict:
    return {
        "manifestVersion": 2,
        "id": "fixture.backend",
        "version": "1.0.0",
        "name": {"zh-CN": "后端模块", "en-US": "Backend module"},
        "description": {"zh-CN": "测试", "en-US": "Test"},
        "publisher": "Lumina Layer Studio",
        "workshopApi": {"min": "1.1.0", "maxExclusive": "2.0.0"},
        "luminaVersion": {"min": "2.0.0"},
        "entrypoints": {"ui": "ui/index.html"},
        "permissions": [],
        "backend": {
            "entry": "backend/main.py",
            "python": "3.12",
            "lock": "backend/pylock.toml",
            "platforms": ["windows-x86_64", "linux-x86_64"],
            "capabilities": [{"name": "network", "reason": "Fetch samples."}],
        },
    }


def write_package(tmp_path: Path, manifest: dict, files: dict[str, bytes]) -> Path:
    path = tmp_path / f"{manifest['id']}-{manifest['version']}.lumina-workshop"
    entries = {
        "manifest.json": json.dumps(manifest).encode("utf-8"),
        "ui/index.html": b"<!doctype html><html><head></head><body></body></html>",
        "assets/icon.png": PNG_1X1,
        "README.md": b"# readme\n",
        "LICENSE": b"MIT\n",
        **files,
    }
    with ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def test_v2_backend_package_is_inspected_like_the_host(tmp_path: Path) -> None:
    files = {"backend/main.py": MAIN, "backend/pylock.toml": LOCK.encode()}
    inspected = inspect_package(write_package(tmp_path, backend_manifest(), files))
    assert isinstance(inspected.manifest, WorkshopManifestV2)


@pytest.mark.parametrize(
    "files",
    [
        {
            "backend/main.py": MAIN,
            "backend/pylock.toml": LOCK.encode(),
            "backend/native.pyd": b"MZ",
        },
        {
            "backend/main.py": MAIN,
            "backend/pylock.toml": LOCK.replace("https://", "http://").encode(),
        },
        {"backend/main.py": MAIN},
    ],
)
def test_backend_packages_reject_native_code_insecure_locks_and_missing_files(
    tmp_path: Path, files: dict[str, bytes]
) -> None:
    with pytest.raises(PackageInspectionError):
        inspect_package(write_package(tmp_path, backend_manifest(), files))


def test_backend_manifest_requires_backend_api() -> None:
    manifest = backend_manifest()
    manifest["workshopApi"] = {"min": "1.0.0", "maxExclusive": "2.0.0"}
    with pytest.raises(ValidationError):
        WorkshopManifestV2.model_validate(manifest)


def test_backend_manifest_accepts_project_snapshots_like_v1() -> None:
    manifest = backend_manifest()
    manifest["projectSnapshots"] = {"protocol": 1, "schemas": ["editor/v1"]}
    with pytest.raises(ValidationError, match=r"project\.storage"):
        WorkshopManifestV2.model_validate(manifest)
    manifest["permissions"] = [
        {"name": "project.storage", "reason": "Keep the editor state."}
    ]
    snapshots = WorkshopManifestV2.model_validate(manifest).project_snapshots
    assert snapshots is not None and snapshots.schemas == ("editor/v1",)


def reviewed_source(valid_source: dict, *, state: str = "active") -> dict:
    source = deepcopy(valid_source)
    version = source["versions"][0]
    version["sha256"] = "0123456789abcdef" * 4
    version["manifestSha256"] = "fedcba9876543210" * 4
    version["workshopApi"] = {"min": "1.1.0", "maxExclusive": "2.0.0"}
    version["backendReview"] = {
        "scope": "backend-code",
        "reviewer": "shmx",
        "reviewedAt": "2026-11-04",
    }
    if state == "blocked":
        version["state"] = "blocked"
        version["revocation"] = {
            "reasonCode": "abuse",
            "severity": "high",
            "message": {"zh-CN": "阻止", "en-US": "Blocked"},
        }
    return source


def backend_release(source: ModuleSource, version: object) -> SimpleNamespace:
    release = release_for(source, version)
    release.package.manifest.manifest_version = 2
    release.package.manifest.backend = object()
    return release


def test_reviews_are_published_separately_and_v1_index_is_unchanged(
    tmp_path: Path, valid_source: dict
) -> None:
    reviewed = reviewed_source(valid_source)
    plain = deepcopy(reviewed)
    del plain["versions"][0]["backendReview"]
    write_source(tmp_path / "reviewed", reviewed)
    write_source(tmp_path / "plain", plain)
    index, reviews = build_registry_outputs(
        tmp_path / "reviewed", generated_at=GENERATED_AT, inspector=backend_release
    )
    plain_index = build_registry(
        tmp_path / "plain", generated_at=GENERATED_AT, inspector=backend_release
    )
    assert index == plain_index
    assert b"backendReview" not in index
    # Older hosts parse the v1 index with this closed model.
    RegistryIndex.model_validate_json(index)
    parsed = ReviewIndex.model_validate_json(reviews)
    assert [(item.module_id, item.version, item.sha256) for item in parsed.reviews] == [
        ("lumina.bead-pattern", "1.0.0", "0123456789abcdef" * 4)
    ]
    assert reviews.endswith(b"\n")


def test_review_requires_a_backend_package_and_skips_blocked_versions(
    tmp_path: Path, valid_source: dict
) -> None:
    write_source(tmp_path / "frontend", reviewed_source(valid_source))
    with pytest.raises(RegistryBuildError, match="manifest v2"):
        build_registry_outputs(
            tmp_path / "frontend", generated_at=GENERATED_AT, inspector=release_for
        )
    write_source(tmp_path / "blocked", reviewed_source(valid_source, state="blocked"))
    _index, reviews = build_registry_outputs(
        tmp_path / "blocked", generated_at=GENERATED_AT, inspector=backend_release
    )
    assert ReviewIndex.model_validate_json(reviews).reviews == ()


def test_pages_publish_reviews_as_a_signed_pair(tmp_path: Path) -> None:
    for name in ("index.json", "index.sig", "reviews.json", "reviews.sig"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    output = tmp_path / "pages"
    build_pages(
        index=tmp_path / "index.json",
        signature=tmp_path / "index.sig",
        reviews=tmp_path / "reviews.json",
        reviews_signature=tmp_path / "reviews.sig",
        output=output,
    )
    assert sorted(path.name for path in output.iterdir()) == [
        "index.html",
        "registry-v1.json",
        "registry-v1.sig",
        "reviews-v1.json",
        "reviews-v1.sig",
    ]
    with pytest.raises(ValueError):
        build_pages(
            index=tmp_path / "index.json",
            signature=tmp_path / "index.sig",
            reviews=tmp_path / "reviews.json",
            output=output,
        )
