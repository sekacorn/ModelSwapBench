"""Small, dependency-free statistics helpers used across scoring."""

from __future__ import annotations

from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile (``pct`` in [0, 100]). Safe on empty/singleton input."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def rate(numerator: int, denominator: int) -> float:
    """Safe ratio; 0.0 when the denominator is 0."""
    return numerator / denominator if denominator else 0.0
