from __future__ import annotations

from copy import deepcopy

import httpx
import pytest

from scripts.scan_releases import _stable_release_tags
from workshop_registry.models import ModuleSource
from workshop_registry.release import ReleaseInspectionError


class FakeClient(httpx.Client):
    def __init__(self, payload: object) -> None:
        self.requests: list[tuple[str, dict[str, int]]] = []
        super().__init__(transport=httpx.MockTransport(self.handle))
        self.payload = payload

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            (
                str(request.url.copy_with(query=None)),
                {"per_page": int(request.url.params["per_page"])},
            )
        )
        return httpx.Response(200, json=self.payload)


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


def test_stable_release_tags_follow_github_repository_transfer(
    valid_source: dict,
) -> None:
    source = ModuleSource.model_validate(valid_source)
    requested_urls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.startswith("/repos/"):
            return httpx.Response(
                301,
                headers={
                    "Location": "https://api.github.com/repositories/123/releases?per_page=100"
                },
            )
        return httpx.Response(200, json=[release("v1.0.1")])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert _stable_release_tags(source, client=client) == ("v1.0.1",)

    assert requested_urls[-1] == (
        "https://api.github.com/repositories/123/releases?per_page=100"
    )


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/releases",
        "http://api.github.com/repositories/123/releases",
        "https://api.github.com:444/repositories/123/releases",
        "https://token@api.github.com/repositories/123/releases",
    ],
)
def test_scanner_rejects_redirect_outside_github_api(
    valid_source: dict,
    location: str,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(301, headers={"Location": location})

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(ReleaseInspectionError, match="GitHub API"),
    ):
        _stable_release_tags(
            ModuleSource.model_validate(valid_source), client=client
        )

    assert len(requests) == 1


def test_scanner_redirect_loop_is_bounded(valid_source: dict) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(301, headers={"Location": str(request.url)})

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(ReleaseInspectionError, match="too many times"),
    ):
        _stable_release_tags(
            ModuleSource.model_validate(valid_source), client=client
        )

    assert len(requests) == 6


def test_scanner_metadata_size_is_bounded(valid_source: dict, monkeypatch) -> None:
    from workshop_registry import release as release_module

    monkeypatch.setattr(release_module, "MAX_RELEASE_METADATA_BYTES", 8)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200, content=b"[" + b" " * 8 + b"]"
                )
            )
        ) as client,
        pytest.raises(ReleaseInspectionError, match="size limit"),
    ):
        _stable_release_tags(
            ModuleSource.model_validate(valid_source), client=client
        )
