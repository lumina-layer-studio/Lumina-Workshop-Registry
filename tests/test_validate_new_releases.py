from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from scripts import validate_new_releases


def write_source(directory: Path, value: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    module_id = value["moduleId"]
    (directory / f"{module_id}.json").write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def test_validation_reinspects_only_appended_versions(
    tmp_path: Path,
    valid_source: dict,
    monkeypatch,
) -> None:
    base = tmp_path / "base"
    head = tmp_path / "head"
    write_source(base, valid_source)
    changed = deepcopy(valid_source)
    appended = deepcopy(changed["versions"][0])
    appended.update(
        {
            "version": "1.1.0",
            "releaseTag": "v1.1.0",
            "assetName": (
                "lumina.bead-pattern-1.1.0.lumina-workshop"
            ),
            "sha256": "c" * 64,
            "manifestSha256": "d" * 64,
        }
    )
    changed["versions"].append(appended)
    write_source(head, changed)
    inspected: list[str] = []
    monkeypatch.setattr(
        validate_new_releases,
        "_assert_exact",
        lambda _source, version: inspected.append(version.version),
    )

    validate_new_releases.validate_new_releases(base, head)

    assert inspected == ["1.1.0"]


def test_validation_reinspects_every_version_of_new_module(
    tmp_path: Path,
    valid_source: dict,
    monkeypatch,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    head = tmp_path / "head"
    write_source(head, valid_source)
    inspected: list[str] = []
    monkeypatch.setattr(
        validate_new_releases,
        "_assert_exact",
        lambda source, version: inspected.append(
            f"{source.module_id}@{version.version}"
        ),
    )

    validate_new_releases.validate_new_releases(base, head)

    assert inspected == ["lumina.bead-pattern@1.0.0"]
