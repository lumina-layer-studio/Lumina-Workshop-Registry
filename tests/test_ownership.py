from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from workshop_registry.ownership import OwnershipError, compare_ownership

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def source_directories(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "base"
    head = tmp_path / "head"
    shutil.copytree(FIXTURES / "base-sources", base)
    shutil.copytree(FIXTURES / "head-sources", head)
    return base, head


def read_source(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_source(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_unchanged_sources_are_allowed(
    source_directories: tuple[Path, Path],
) -> None:
    compare_ownership(*source_directories)


def test_existing_module_cannot_change_repository_in_normal_pr(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source["repository"] = "https://github.com/attacker/takeover"
    write_source(path, source)

    with pytest.raises(OwnershipError, match="ownership transfer"):
        compare_ownership(base, head)


def test_existing_versions_are_append_only(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source["versions"][0]["sha256"] = "f" * 64
    write_source(path, source)

    with pytest.raises(OwnershipError, match="immutable version"):
        compare_ownership(base, head)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("official", True),
        ("publisher", "Different Publisher"),
    ],
)
def test_existing_identity_metadata_is_immutable(
    source_directories: tuple[Path, Path],
    field: str,
    value: object,
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source[field] = value
    write_source(path, source)

    with pytest.raises(OwnershipError, match="identity metadata"):
        compare_ownership(base, head)


def test_existing_module_cannot_be_deleted(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    (head / "fixture.hello.json").unlink()
    with pytest.raises(OwnershipError, match="cannot be deleted"):
        compare_ownership(base, head)


def test_version_order_cannot_change(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source["versions"].reverse()
    write_source(path, source)

    with pytest.raises(OwnershipError, match="version order"):
        compare_ownership(base, head)


def test_new_versions_may_only_append(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    appended = deepcopy(source["versions"][-1])
    appended.update(
        {
            "version": "1.2.0",
            "releaseTag": "v1.2.0",
            "assetName": "fixture.hello-1.2.0.lumina-workshop",
            "sha256": (
                "23456789abcdef0123456789abcdef"
                "0123456789abcdef0123456789abcdef01"
            ),
            "manifestSha256": (
                "cdef0123456789abcdef0123456789"
                "abcdef0123456789abcdef0123456789ab"
            ),
        }
    )
    source["versions"].append(appended)
    write_source(path, source)
    compare_ownership(base, head)


def test_existing_version_may_be_blocked_with_complete_revocation(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source["versions"][0]["state"] = "blocked"
    source["versions"][0]["revocation"] = {
        "reasonCode": "malware",
        "severity": "critical",
        "message": {
            "zh-CN": "此版本已被阻止。",
            "en-US": "This version has been blocked.",
        },
    }
    write_source(path, source)
    compare_ownership(base, head)


def test_other_existing_version_state_mutations_are_rejected(
    source_directories: tuple[Path, Path],
) -> None:
    base, head = source_directories
    path = head / "fixture.hello.json"
    source = read_source(path)
    source["versions"][0]["state"] = "deprecated"
    write_source(path, source)

    with pytest.raises(OwnershipError, match="immutable version"):
        compare_ownership(base, head)
