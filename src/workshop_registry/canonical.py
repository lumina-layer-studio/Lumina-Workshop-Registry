"""Canonical UTF-8 JSON encoding used by Registry indexes and signatures."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


class CanonicalJsonError(ValueError):
    """A value cannot be represented by the Registry canonical format."""


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise CanonicalJsonError(
            "Registry canonical JSON does not permit floating numbers"
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError(
                    "Registry canonical JSON requires string object keys"
                )
            _reject_floats(item)
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for item in value:
            _reject_floats(item)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode one JSON value with sorted keys and one trailing newline."""

    _reject_floats(value)
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalJsonError(
            "value cannot be encoded as canonical Registry JSON"
        ) from exc

