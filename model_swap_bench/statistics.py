"""Deterministic statistical evidence for replacement decisions."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ConfidenceInterval(_Strict):
    lower: float
    upper: float
    confidence: float = 0.95
    method: str
    sample_size: int


class DistributionEvidence(_Strict):
    sample_size: int
    mean: float | None
    median: float | None
    p90: float | None
    p95: float | None
    minimum: float | None
    maximum: float | None
    outlier_count: int
    mean_confidence_interval: ConfidenceInterval | None = None


class PairedComparison(_Strict):
    sample_size: int
    mean_difference: float | None
    wins: int
    ties: int
    losses: int
    confidence_interval: ConfidenceInterval | None
    sufficient_evidence: bool
    warnings: list[str] = Field(default_factory=list)


def _rounded(value: float) -> float:
    return round(value, 4)


def percentile(values: Sequence[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return _rounded(ordered[lower])
    fraction = position - lower
    return _rounded(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def wilson_interval(successes: int, total: int, *, confidence: float = 0.95) -> ConfidenceInterval | None:
    if total <= 0 or successes < 0 or successes > total:
        return None
    z = 1.959963984540054 if confidence == 0.95 else 1.6448536269514722
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return ConfidenceInterval(
        lower=_rounded(max(0.0, center - margin)),
        upper=_rounded(min(1.0, center + margin)),
        confidence=confidence,
        method="wilson",
        sample_size=total,
    )


def bootstrap_mean_interval(
    values: Sequence[float], *, confidence: float = 0.95, seed: int = 1729, samples: int = 1000
) -> ConfidenceInterval | None:
    if not values:
        return None
    rng = random.Random(seed)  # nosec B311  # noqa: S311 - deterministic statistical resampling
    means = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(samples)]
    tail = (1 - confidence) / 2
    lower = percentile(means, tail * 100)
    upper = percentile(means, (1 - tail) * 100)
    if lower is None or upper is None:
        return None
    return ConfidenceInterval(lower=lower, upper=upper, confidence=confidence, method="deterministic-bootstrap", sample_size=len(values))


def describe(values: Sequence[float], *, seed: int = 1729) -> DistributionEvidence:
    if not values:
        return DistributionEvidence(sample_size=0, mean=None, median=None, p90=None, p95=None, minimum=None, maximum=None, outlier_count=0)
    ordered = sorted(values)
    q1 = percentile(ordered, 25) or 0.0
    q3 = percentile(ordered, 75) or 0.0
    iqr = q3 - q1
    outliers = sum(value < q1 - 1.5 * iqr or value > q3 + 1.5 * iqr for value in ordered)
    return DistributionEvidence(
        sample_size=len(ordered),
        mean=_rounded(sum(ordered) / len(ordered)),
        median=percentile(ordered, 50),
        p90=percentile(ordered, 90),
        p95=percentile(ordered, 95),
        minimum=_rounded(ordered[0]),
        maximum=_rounded(ordered[-1]),
        outlier_count=outliers,
        mean_confidence_interval=bootstrap_mean_interval(ordered, seed=seed),
    )


def paired_comparison(
    baseline: Sequence[float], candidate: Sequence[float], *, minimum_sample_size: int = 20, seed: int = 1729
) -> PairedComparison:
    if len(baseline) != len(candidate):
        raise ValueError("paired samples must have equal length")
    differences = [candidate_value - baseline_value for baseline_value, candidate_value in zip(baseline, candidate, strict=True)]
    warnings: list[str] = []
    if len(differences) < minimum_sample_size:
        warnings.append(f"insufficient evidence: {len(differences)} paired cases; minimum is {minimum_sample_size}")
    return PairedComparison(
        sample_size=len(differences),
        mean_difference=_rounded(sum(differences) / len(differences)) if differences else None,
        wins=sum(value > 0 for value in differences),
        ties=sum(value == 0 for value in differences),
        losses=sum(value < 0 for value in differences),
        confidence_interval=bootstrap_mean_interval(differences, seed=seed),
        sufficient_evidence=len(differences) >= minimum_sample_size,
        warnings=warnings,
    )
