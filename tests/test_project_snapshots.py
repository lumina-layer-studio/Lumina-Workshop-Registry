import pytest
from pydantic import ValidationError

from tests.test_package import valid_manifest
from workshop_registry.models import WorkshopManifest


def test_snapshot_capability_is_optional_and_requires_storage_permission():
    value = valid_manifest()
    assert WorkshopManifest.model_validate(value).project_snapshots is None
    value["projectSnapshots"] = {"protocol": 1, "schemas": ["bead-workspace/v1"]}
    assert WorkshopManifest.model_validate(value).project_snapshots.schemas == (
        "bead-workspace/v1",
    )
    value["permissions"] = []
    with pytest.raises(ValidationError, match=r"project\.storage"):
        WorkshopManifest.model_validate(value)


@pytest.mark.parametrize(
    "capability",
    [
        {"protocol": 2, "schemas": ["editor/v1"]},
        {"protocol": 1, "schemas": []},
        {"protocol": 1, "schemas": ["editor/v1", "editor/v1"]},
        {"protocol": 1, "schemas": ["x" * 129]},
    ],
)
def test_snapshot_schema_limits(capability):
    value = valid_manifest()
    value["projectSnapshots"] = capability
    with pytest.raises(ValidationError):
        WorkshopManifest.model_validate(value)
