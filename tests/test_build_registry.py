from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.build_registry import RegistryBuildError, build_registry
from workshop_registry.models import ModuleSource


def write_source(directory: Path, value: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{value['moduleId']}.json"
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def release_for(source: ModuleSource, version) -> SimpleNamespace:
    manifest = SimpleNamespace(
        id=source.module_id,
        version=version.version,
        publisher=source.publisher,
        name=SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "zh-CN": "测试模块",
                "en-US": "Fixture module",
            }
        ),
        description=SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "zh-CN": "确定性构建测试",
                "en-US": "Deterministic build fixture",
            }
        ),
        workshop_api=version.workshop_api,
        lumina_version=version.lumina_version,
        permissions=version.permissions,
    )
    package = SimpleNamespace(
        manifest=manifest,
        manifest_sha256=version.manifest_sha256,
    )
    return SimpleNamespace(
        asset_name=version.asset_name,
        download_url=(
            f"{source.repository}/releases/download/"
            f"{version.release_tag}/{version.asset_name}"
        ),
        asset_bytes=version.asset_bytes,
        sha256=version.sha256,
        manifest_sha256=version.manifest_sha256,
        package=package,
    )


@pytest.fixture
def source_directory(tmp_path: Path, valid_source: dict) -> Path:
    source = deepcopy(valid_source)
    source["versions"][0]["sha256"] = (
        "0123456789abcdef0123456789abcdef"
        "0123456789abcdef0123456789abcdef"
    )
    source["versions"][0]["manifestSha256"] = (
        "abcdef0123456789abcdef0123456789"
        "abcdef0123456789abcdef0123456789"
    )
    directory = tmp_path / "modules"
    write_source(directory, source)
    return directory


def test_build_is_deterministic(source_directory: Path) -> None:
    first = build_registry(
        source_directory,
        generated_at="2026-07-30T00:00:00Z",
        inspector=release_for,
    )
    second = build_registry(
        source_directory,
        generated_at="2026-07-30T00:00:00Z",
        inspector=release_for,
    )

    assert first == second
    assert first.endswith(b"\n")
    assert not first.endswith(b"\n\n")
    assert b"\\u6d4b\\u8bd5" not in first
    assert "测试模块".encode() in first


def test_build_orders_modules_lexically(
    source_directory: Path,
    valid_source: dict,
) -> None:
    earlier = deepcopy(valid_source)
    earlier["moduleId"] = "alpha.module"
    earlier["repository"] = "https://github.com/example/alpha-module"
    earlier["versions"][0]["assetName"] = (
        "alpha.module-1.0.0.lumina-workshop"
    )
    earlier["versions"][0]["sha256"] = (
        "123456789abcdef0123456789abcdef0"
        "123456789abcdef0123456789abcdef0"
    )
    earlier["versions"][0]["manifestSha256"] = (
        "bcdef0123456789abcdef0123456789a"
        "bcdef0123456789abcdef0123456789a"
    )
    write_source(source_directory, earlier)

    payload = json.loads(
        build_registry(
            source_directory,
            generated_at="2026-07-30T00:00:00Z",
            inspector=release_for,
        )
    )
    assert [
        module["moduleId"] for module in payload["modules"]
    ] == ["alpha.module", "lumina.bead-pattern"]


def test_build_rejects_synthetic_hashes(
    tmp_path: Path,
    valid_source: dict,
) -> None:
    directory = tmp_path / "modules"
    write_source(directory, valid_source)
    with pytest.raises(RegistryBuildError, match="synthetic hash"):
        build_registry(
            directory,
            generated_at="2026-07-30T00:00:00Z",
            inspector=release_for,
        )


def test_build_rejects_release_bytes_that_do_not_match_review(
    source_directory: Path,
) -> None:
    def changed(source: ModuleSource, version):
        release = release_for(source, version)
        release.sha256 = "f" * 64
        return release

    with pytest.raises(RegistryBuildError, match="reviewed bytes"):
        build_registry(
            source_directory,
            generated_at="2026-07-30T00:00:00Z",
            inspector=changed,
        )

