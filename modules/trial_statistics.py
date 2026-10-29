"""Small statistical helpers for the weapon simulation reports."""
from __future__ import annotations

import math
from collections.abc import Iterable


def sample_percentile(values: Iterable[float], p: float, *, empty: float = math.nan) -> float:
    """Return the linearly interpolated percentile of sorted observed samples.

    ``p`` is between zero and one. Empty samples return ``empty``; callers
    choose infinity for an unobserved TTK and NaN for other undefined metrics.
    NaN samples are rejected because they have no well-defined sorted order.
    Equal infinities interpolate to the same infinity; between opposite
    infinities the interpolated value is undefined (NaN).
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be between 0 and 1")
    ordered = list(values)
    if any(math.isnan(value) for value in ordered):
        raise ValueError("samples must not contain NaN")
    ordered.sort()
    if not ordered:
        return empty
    position = p * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    low, high = ordered[lower], ordered[upper]
    if lower == upper:
        return low
    if math.isinf(low) and math.isinf(high):
        # Equal infinities stay infinite; opposite infinities have no
        # determined interpolation. Finite equal endpoints fall through to
        # preserve the prior float result for interpolated integer samples.
        return low if low == high else math.nan
    if math.isinf(low):
        return low
    if math.isinf(high):
        return high
    weight = position - lower
    difference = high - low
    if not math.isfinite(difference):
        # Opposite finite extremes can overflow on subtraction even though
        # every interpolated value lies within the representable endpoints.
        return (1.0 - weight) * low + weight * high
    return low + difference * weight
