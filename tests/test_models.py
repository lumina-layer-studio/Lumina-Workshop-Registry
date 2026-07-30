from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from workshop_registry.models import ModuleSource, RegistryIndex

ROOT = Path(__file__).resolve().parents[1]


def test_source_rejects_unknown_fields(valid_source: dict) -> None:
    valid_source["unexpected"] = True
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(valid_source)


def test_version_requires_exact_release_identity(valid_source: dict) -> None:
    version = valid_source["versions"][0]
    assert version == {
        "version": "1.0.0",
        "releaseTag": "v1.0.0",
        "assetName": "lumina.bead-pattern-1.0.0.lumina-workshop",
        "assetBytes": 12345,
        "sha256": "a" * 64,
        "manifestSha256": "b" * 64,
        "workshopApi": {"min": "1.0.0", "maxExclusive": "2.0.0"},
        "luminaVersion": {"min": "2.0.0"},
        "permissions": [
            {"name": "image.pick", "reason": "选择并读取拼豆图纸或截图"},
        ],
        "state": "active",
        "revocation": None,
    }
    ModuleSource.model_validate(valid_source)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("versions", 0, "version"), "1"),
        (("versions", 0, "version"), "01.0.0"),
        (("versions", 0, "sha256"), "A" * 64),
        (("versions", 0, "sha256"), "a" * 63),
        (("repository",), "http://github.com/example/module"),
        (("repository",), "https://gitlab.com/example/module"),
        (("repository",), "https://github.com/example/module.git"),
    ],
)
def test_source_rejects_noncanonical_identity(
    valid_source: dict,
    path: tuple,
    value: object,
) -> None:
    target = valid_source
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(valid_source)


def test_asset_name_and_release_tag_match_module_version(
    valid_source: dict,
) -> None:
    for field, value in (
        ("releaseTag", "v1.0.1"),
        ("assetName", "other-1.0.0.lumina-workshop"),
    ):
        changed = deepcopy(valid_source)
        changed["versions"][0][field] = value
        with pytest.raises(ValidationError):
            ModuleSource.model_validate(changed)


def test_permissions_are_known_unique_and_explained(
    valid_source: dict,
) -> None:
    changed = deepcopy(valid_source)
    changed["versions"][0]["permissions"][0]["name"] = "network.fetch"
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(changed)

    changed = deepcopy(valid_source)
    changed["versions"][0]["permissions"][0]["reason"] = "   "
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(changed)

    changed = deepcopy(valid_source)
    changed["versions"][0]["permissions"] *= 2
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(changed)


def test_state_and_revocation_are_consistent(valid_source: dict) -> None:
    blocked = deepcopy(valid_source)
    blocked["versions"][0]["state"] = "blocked"
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(blocked)

    active_with_revocation = deepcopy(valid_source)
    active_with_revocation["versions"][0]["revocation"] = {
        "reasonCode": "malware",
        "severity": "critical",
        "message": {
            "zh-CN": "此版本已被阻止。",
            "en-US": "This version has been blocked.",
        },
    }
    with pytest.raises(ValidationError):
        ModuleSource.model_validate(active_with_revocation)


def test_versions_must_be_strictly_increasing(valid_source: dict) -> None:
    valid_source["versions"].append(
        deepcopy(valid_source["versions"][0]),
    )
    with pytest.raises(ValidationError, match="increasing"):
        ModuleSource.model_validate(valid_source)


def test_registry_rejects_duplicate_module_versions(
    valid_index: dict,
) -> None:
    valid_index["modules"].append(
        deepcopy(valid_index["modules"][0]),
    )
    with pytest.raises(ValidationError, match="duplicate module"):
        RegistryIndex.model_validate(valid_index)


def test_registry_requires_exact_download_url(valid_index: dict) -> None:
    valid_index["modules"][0]["versions"][0]["downloadUrl"] = (
        "https://github.com/attacker/repo/releases/download/"
        "v1.0.0/lumina.bead-pattern-1.0.0.lumina-workshop"
    )
    with pytest.raises(ValidationError, match="downloadUrl"):
        RegistryIndex.model_validate(valid_index)


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (ModuleSource, "module-source-v1.schema.json"),
        (RegistryIndex, "registry-v1.schema.json"),
    ],
)
def test_checked_json_schemas_match_models(model, filename: str) -> None:
    expected = (
        json.dumps(
            model.model_json_schema(by_alias=True),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    actual = (ROOT / "schemas" / filename).read_text(encoding="utf-8")
    assert actual == expected
