from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ALLOWED_ACTIONS = {
    (
        "actions/checkout@"
        "11d5960a326750d5838078e36cf38b85af677262"
    ),
    (
        "actions/setup-python@"
        "a26af69be951a213d495a4c3e4e4022e16d87065"
    ),
    (
        "actions/upload-artifact@"
        "ea165f8d65b6e75b540449e92b4886f43607fa02"
    ),
    (
        "actions/configure-pages@"
        "983d7736d9b0ae728b81ab479565c72886d7745b"
    ),
    (
        "actions/upload-pages-artifact@"
        "56afc609e74202658d3ffba0e8f6dda462b719fa"
    ),
    (
        "actions/deploy-pages@"
        "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e"
    ),
}


def workflow(name: str) -> tuple[str, dict]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(text.replace("\non:", "\n'on':", 1))
    return text, parsed


def used_actions(value: object) -> set[str]:
    output: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "uses" and isinstance(item, str):
                output.add(item)
            output.update(used_actions(item))
    elif isinstance(value, list):
        for item in value:
            output.update(used_actions(item))
    return output


@pytest.mark.parametrize(
    "filename",
    [
        "pull-request.yml",
        "scan-releases.yml",
        "publish-pages.yml",
    ],
)
def test_every_third_party_action_is_exactly_allowlisted(
    filename: str,
) -> None:
    _text, parsed = workflow(filename)
    assert used_actions(parsed) <= ALLOWED_ACTIONS
    assert all(
        re.fullmatch(r"[^@]+@[0-9a-f]{40}", action)
        for action in used_actions(parsed)
    )


def test_pull_request_validation_is_read_only_and_complete() -> None:
    text, parsed = workflow("pull-request.yml")
    assert parsed["on"] == {"pull_request": None}
    assert parsed["permissions"] == {"contents": "read"}
    assert "REGISTRY_ED25519_PRIVATE_KEY" not in text
    assert "pip install --require-hashes -r requirements.lock" in text
    assert "scripts/validate_sources.py" in text
    assert "scripts/check_ownership_diff.py" in text
    assert "scripts/validate_new_releases.py" in text
    assert text.count("scripts/build_registry.py") >= 2
    assert "cmp " in text
    assert "candidate-registry-v1.json" in text


def test_scanner_can_only_open_a_reviewable_source_pr() -> None:
    text, parsed = workflow("scan-releases.yml")
    assert set(parsed["on"]) == {"schedule", "workflow_dispatch"}
    assert parsed["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert "scripts/scan_releases.py" in text
    assert "gh pr create" in text
    assert "gh pr merge" not in text
    assert "REGISTRY_ED25519_PRIVATE_KEY" not in text
    assert "deploy-pages" not in text


def test_publish_only_signs_protected_main() -> None:
    text, parsed = workflow("publish-pages.yml")
    assert parsed["on"] == {
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    job = parsed["jobs"]["publish"]
    assert job["environment"]["name"] == "registry-production"
    assert job["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert text.count("REGISTRY_ED25519_PRIVATE_KEY") == 2
    assert "scripts/sign_registry.py" in text
    assert text.count("scripts/verify_registry.py") >= 2
    assert "find pages -maxdepth 1 -type f" in text
    assert '"3"' in text
    assert "pages/registry-v1.json" in text
    assert "pages/registry-v1.sig" in text
    assert "pages/index.html" in text
    assert "actions/upload-pages-artifact@" in text
    assert "actions/deploy-pages@" in text

