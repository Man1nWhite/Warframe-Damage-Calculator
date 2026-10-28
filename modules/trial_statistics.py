"""Small statistical helpers for the weapon simulation reports."""
from __future__ import annotations

import math
from collections.abc import Iterable


def sample_percentile(values: Iterable[float], p: float, *, empty: float = math.nan) -> float:
    """Return the linearly interpolated percentile of sorted observed samples.

    ``p`` is between zero and one. Empty samples return ``empty``; callers
    choose infinity for an unobserved TTK and NaN for other undefined metrics.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be between 0 and 1")
    ordered = sorted(values)
    if not ordered:
        return empty
    position = p * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
