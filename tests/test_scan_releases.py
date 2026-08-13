from __future__ import annotations

from copy import deepcopy

from scripts.scan_releases import _stable_release_tags
from workshop_registry.models import ModuleSource


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests: list[tuple[str, dict[str, int]]] = []

    def get(self, url: str, *, params: dict[str, int]) -> FakeResponse:
        self.requests.append((url, params))
        return FakeResponse(self.payload)


def release(
    tag: str,
    *,
    draft: bool = False,
    prerelease: bool = False,
) -> dict[str, object]:
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
    }


def test_stable_release_tags_skip_non_plain_automated_versions(
    valid_source: dict,
) -> None:
    source_value = deepcopy(valid_source)
    source_value["versions"] = []
    source = ModuleSource.model_validate(source_value)
    client = FakeClient(
        [
            release("v1.0.0-rc.1"),
            release("v1.0.0+build.7"),
            release("v1.0.0", prerelease=True),
            release("v1.0.1", draft=True),
            release("v1.0.0"),
        ]
    )

    assert _stable_release_tags(source, client=client) == ("v1.0.0",)
    assert client.requests == [
        (
            "https://api.github.com/repos/lumina-layer-studio/"
            "Lumina-Fuse-Bead-Studio/releases",
            {"per_page": 100},
        )
    ]


def test_stable_release_tags_use_semver_order_and_ignore_existing(
    valid_source: dict,
) -> None:
    source = ModuleSource.model_validate(valid_source)
    client = FakeClient(
        [
            release("v1.10.0"),
            release("v1.2.0"),
            release("not-a-version"),
            release("v1.0.0"),
        ]
    )

    assert _stable_release_tags(source, client=client) == (
        "v1.2.0",
        "v1.10.0",
    )
