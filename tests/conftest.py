from __future__ import annotations

from copy import deepcopy

import pytest


@pytest.fixture
def valid_source() -> dict:
    return {
        "schemaVersion": 1,
        "moduleId": "lumina.bead-pattern",
        "repository": (
            "https://github.com/lumina-layer-studio/"
            "Lumina-Fuse-Bead-Studio"
        ),
        "official": True,
        "publisher": "Lumina Studio",
        "versions": [
            {
                "version": "1.0.0",
                "releaseTag": "v1.0.0",
                "assetName": (
                    "lumina.bead-pattern-1.0.0.lumina-workshop"
                ),
                "assetBytes": 12345,
                "sha256": "a" * 64,
                "manifestSha256": "b" * 64,
                "workshopApi": {
                    "min": "1.0.0",
                    "maxExclusive": "2.0.0",
                },
                "luminaVersion": {"min": "2.0.0"},
                "permissions": [
                    {
                        "name": "image.pick",
                        "reason": "选择并读取拼豆图纸或截图",
                    },
                ],
                "state": "active",
                "revocation": None,
            },
        ],
    }


@pytest.fixture
def valid_index(valid_source: dict) -> dict:
    source = deepcopy(valid_source)
    version = source["versions"][0]
    version["downloadUrl"] = (
        f"{source['repository']}/releases/download/"
        f"{version['releaseTag']}/{version['assetName']}"
    )
    module = {
        key: source[key]
        for key in (
            "moduleId",
            "repository",
            "official",
            "publisher",
            "versions",
        )
    }
    module["name"] = {
        "zh-CN": "拼豆工作台",
        "en-US": "Fuse Bead Studio",
    }
    module["description"] = {
        "zh-CN": "把清晰图纸变成可编辑拼豆矩阵。",
        "en-US": "Turn clear charts into editable bead matrices.",
    }
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-07-30T00:00:00Z",
        "modules": [module],
    }

