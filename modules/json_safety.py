"""Strict JSON decoding helpers for imported export data."""
from __future__ import annotations

from typing import Any


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build an object while rejecting ambiguous repeated keys at every depth."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate key {key!r}.")
        result[key] = value
    return result
