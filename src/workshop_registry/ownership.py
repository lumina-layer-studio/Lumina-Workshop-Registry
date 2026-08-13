"""Append-only ownership and immutable-version checks for source reviews."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import ModuleSource, SourceVersion


class OwnershipError(ValueError):
    """A reviewed Registry identity or historical release was rewritten."""


def _load_sources(directory: Path) -> dict[str, ModuleSource]:
    sources: dict[str, ModuleSource] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            source = ModuleSource.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
            raise OwnershipError(
                f"version order or source validation failed for {path.name}"
            ) from exc
        expected_name = f"{source.module_id}.json"
        if path.name != expected_name:
            raise OwnershipError(
                f"source filename must remain {expected_name}"
            )
        if source.module_id in sources:
            raise OwnershipError(
                f"duplicate module identity: {source.module_id}"
            )
        sources[source.module_id] = source
    return sources


def _version_dict(version: SourceVersion) -> dict:
    return version.model_dump(by_alias=True, mode="json")


def _is_complete_block_transition(
    previous: SourceVersion,
    current: SourceVersion,
) -> bool:
    if current.state != "blocked" or current.revocation is None:
        return False
    previous_value = _version_dict(previous)
    current_value = _version_dict(current)
    current_value["state"] = previous_value["state"]
    current_value["revocation"] = previous_value["revocation"]
    return current_value == previous_value


def compare_ownership(base_directory: Path, head_directory: Path) -> None:
    """Reject ownership transfer and historical version rewrites."""

    base_sources = _load_sources(base_directory)
    head_sources = _load_sources(head_directory)
    for module_id, previous in base_sources.items():
        current = head_sources.get(module_id)
        if current is None:
            raise OwnershipError(
                f"existing module {module_id} cannot be deleted"
            )
        if current.repository != previous.repository:
            raise OwnershipError(
                f"{module_id} ownership transfer requires maintainer process"
            )
        if (
            current.official != previous.official
            or current.publisher != previous.publisher
        ):
            raise OwnershipError(
                f"{module_id} identity metadata is immutable"
            )
        if len(current.versions) < len(previous.versions):
            raise OwnershipError(
                f"{module_id} immutable version history was truncated"
            )

        for index, previous_version in enumerate(previous.versions):
            current_version = current.versions[index]
            if current_version.version != previous_version.version:
                raise OwnershipError(
                    f"{module_id} version order cannot change"
                )
            if current_version == previous_version:
                continue
            if _is_complete_block_transition(
                previous_version,
                current_version,
            ):
                continue
            raise OwnershipError(
                f"{module_id}@{previous_version.version} "
                "is an immutable version"
            )


def load_source_json(path: Path) -> dict:
    """Read one source record for explicit review tooling."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise OwnershipError("source root must be an object")
    return value

