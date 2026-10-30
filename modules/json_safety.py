"""Strict JSON decoding helpers for imported export data."""
from __future__ import annotations

from typing import IO, Any

# The bundled upgrade JSON is ~6 MiB; this leaves substantial room to grow.
MAX_EXPORT_JSON_BYTES = 128 * 1024 * 1024


def read_bounded(stream: IO[bytes], limit: int, description: str) -> bytes:
    """Read at most ``limit`` bytes without trusting a file's stated size."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise ValueError(f"{description} exceeds the {limit}-byte safety limit.")
        chunks.append(chunk)


def require_json_depth(text: str, max_depth: int, description: str) -> None:
    """Bound JSON container nesting before decoding, independently of Python.

    Brackets and braces in strings do not count; backslash-escaped characters
    cannot end a string. Syntax validation remains the JSON decoder's job.

    Unbalanced closing brackets cannot be used to buy headroom: the running
    depth stops at zero, so ``]]]]`` followed by deeply nested arrays still
    trips the limit instead of starting from a negative count.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                raise ValueError(f"{description} exceeds the maximum nesting depth of {max_depth}.")
        elif char in "]}":
            depth = max(depth - 1, 0)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build an object while rejecting ambiguous repeated keys at every depth."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON object contains duplicate key {key!r}.")
        result[key] = value
    return result
