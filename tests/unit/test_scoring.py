from __future__ import annotations

from model_swap_bench.config.models import ModelCandidate, ProviderKind, ReplacementConfig, ScoringConfig
from model_swap_bench.results import ModelSummary
from model_swap_bench.scoring import economics, metrics
from model_swap_bench.scoring.replacement import (
    INSUFFICIENT_EVIDENCE,
    NOT_RECOMMENDED,
    RECOMMENDED,
    decide_replacement,
)


def test_metrics() -> None:
    assert metrics.median([1, 2, 3]) == 2
    assert metrics.median([1, 2, 3, 4]) == 2.5
    assert metrics.percentile([], 95) == 0.0
    assert metrics.percentile([10], 95) == 10
    assert abs(metrics.percentile([0, 100], 50) - 50) < 1e-9
    assert metrics.rate(1, 0) == 0.0


def test_cost_per_success_zero_safe() -> None:
    assert economics.cost_per_success(1.0, 0) is None
    assert economics.cost_per_success(2.0, 4) == 0.5


def test_token_and_compute_cost() -> None:
    cand = ModelCandidate(
        alias="a", provider=ProviderKind.OLLAMA, model="m", estimated_input_cost_per_million=10.0, estimated_output_cost_per_million=30.0
    )
    assert economics.token_cost(cand, 1_000_000, 0) == 10.0
    zero = economics.compute_cost(ScoringConfig(), 1000)
    assert zero == 0.0


def _summary(alias: str, success: float, quality: float, cost_per_success: float | None) -> ModelSummary:
    return ModelSummary(
        model_alias=alias,
        provider="deterministic",
        deployment="local",
        total_cases=5,
        successful_cases=int(success * 5),
        success_rate=success,
        quality_score=quality,
        cost_per_success_usd=cost_per_success,
        policy_pass_rate=1.0,
        valid_json_rate=1.0,
    )


def _cand(alias: str, hosted: bool = False) -> ModelCandidate:
    return ModelCandidate(alias=alias, provider=ProviderKind.DETERMINISTIC, model="m", deployment="hosted" if hosted else "local")


def test_replacement_recommended() -> None:
    base = _summary("base", 1.0, 1.0, 0.01)
    cand = _summary("cand", 1.0, 1.0, 0.001)
    cfg = ReplacementConfig(baseline="base", candidates=["cand"], maximum_quality_drop=0.05, minimum_cost_reduction=0.2)
    d = decide_replacement(base, cand, _cand("cand"), cfg, candidate_constraints=[], privacy_allows_hosted=False)
    assert d.recommendation == RECOMMENDED
    assert d.eligible


def test_replacement_not_recommended_quality() -> None:
    base = _summary("base", 1.0, 1.0, 0.01)
    cand = _summary("cand", 0.6, 0.6, 0.0)
    cfg = ReplacementConfig(baseline="base", candidates=["cand"])
    d = decide_replacement(base, cand, _cand("cand"), cfg, candidate_constraints=[], privacy_allows_hosted=False)
    assert d.recommendation == NOT_RECOMMENDED
    assert d.failed_constraints


def test_replacement_insufficient_evidence() -> None:
    base = _summary("base", 1.0, 1.0, 0.01)
    cand = ModelSummary(model_alias="cand", provider="deterministic", deployment="local", total_cases=0)
    cfg = ReplacementConfig(baseline="base", candidates=["cand"])
    d = decide_replacement(base, cand, _cand("cand"), cfg, candidate_constraints=[], privacy_allows_hosted=False)
    assert d.recommendation == INSUFFICIENT_EVIDENCE


def test_replacement_hosted_blocked() -> None:
    base = _summary("base", 1.0, 1.0, 0.01)
    cand = _summary("cand", 1.0, 1.0, 0.0)
    cfg = ReplacementConfig(baseline="base", candidates=["cand"], minimum_cost_reduction=0.0)
    d = decide_replacement(base, cand, _cand("cand", hosted=True), cfg, candidate_constraints=[], privacy_allows_hosted=False)
    assert not d.deployment_compatible
    assert d.recommendation == NOT_RECOMMENDED
