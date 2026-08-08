"""Transparent, rules-based replacement decision engine.

A candidate is recommended only when every required gate passes. The decision
always carries its evidence and the specific constraints that failed — failures
are never hidden behind an aggregate score.
"""

from __future__ import annotations

from model_swap_bench.config.models import ModelCandidate, ReplacementConfig
from model_swap_bench.results import CascadeSummary, ConstraintResult, ModelSummary, ReplacementDecision

# Recommendation strings (stable, referenced by reports/docs).
RECOMMENDED = "recommended replacement"
RECOMMENDED_WITH_CONDITIONS = "recommended with conditions"
FIRST_STAGE_WITH_ESCALATION = "suitable as first-stage model with escalation"
NOT_RECOMMENDED = "not recommended"
INSUFFICIENT_EVIDENCE = "insufficient evidence"


def _cost_reduction_ratio(baseline: ModelSummary, candidate: ModelSummary) -> float | None:
    """Fractional cost reduction using cost-per-success, falling back to total cost."""
    b_cps, c_cps = baseline.cost_per_success_usd, candidate.cost_per_success_usd
    if b_cps is not None and c_cps is not None and b_cps > 0:
        return (b_cps - c_cps) / b_cps
    if baseline.total_cost_usd > 0:
        return (baseline.total_cost_usd - candidate.total_cost_usd) / baseline.total_cost_usd
    return None


def decide_replacement(
    baseline: ModelSummary,
    candidate: ModelSummary,
    candidate_model: ModelCandidate,
    config: ReplacementConfig,
    *,
    candidate_constraints: list[ConstraintResult],
    privacy_allows_hosted: bool,
    cascade: CascadeSummary | None = None,
) -> ReplacementDecision:
    quality_delta = candidate.quality_score - baseline.quality_score
    quality_drop = max(0.0, baseline.quality_score - candidate.quality_score)
    cost_ratio = _cost_reduction_ratio(baseline, candidate)
    cost_delta = (
        None
        if baseline.cost_per_success_usd is None or candidate.cost_per_success_usd is None
        else (candidate.cost_per_success_usd - baseline.cost_per_success_usd)
    )
    latency_delta = candidate.avg_latency_ms - baseline.avg_latency_ms
    reliability_delta = candidate.success_rate - baseline.success_rate
    policy_pass = candidate.policy_pass_rate >= 1.0
    deployment_compatible = (not candidate_model.is_hosted) or privacy_allows_hosted

    failed: list[str] = []
    risks: list[str] = []
    evidence: list[str] = [
        f"{candidate.success_rate * 100:.0f}% direct success ({candidate.successful_cases}/{candidate.total_cases})",
        f"quality {candidate.quality_score:.2f} vs baseline {baseline.quality_score:.2f} (drop {quality_drop:.2f})",
    ]

    if quality_drop > config.maximum_quality_drop:
        failed.append(f"quality drop {quality_drop:.2f} > allowed {config.maximum_quality_drop:.2f}")
    # A large success-rate drop is a failure even if per-evaluator quality stays high —
    # never hide a failed case behind an averaged score.
    if -reliability_delta > config.maximum_quality_drop:
        failed.append(f"success-rate drop {-reliability_delta:.2f} > allowed {config.maximum_quality_drop:.2f}")
    if config.minimum_reliability is not None and candidate.success_rate < config.minimum_reliability:
        failed.append(f"success rate {candidate.success_rate:.2f} < required {config.minimum_reliability:.2f}")
    if config.maximum_latency_ms is not None and candidate.p95_latency_ms > config.maximum_latency_ms:
        failed.append(f"p95 latency {candidate.p95_latency_ms:.0f}ms > allowed {config.maximum_latency_ms:.0f}ms")
    if not policy_pass:
        failed.append(f"policy pass rate {candidate.policy_pass_rate:.2f} < 1.0")
    if not deployment_compatible:
        failed.append("candidate is a hosted provider but hosted providers are not permitted")
    for c in candidate_constraints:
        if not c.passed:
            failed.append(f"constraint {c.name} failed (actual={c.actual}, threshold={c.threshold})")

    cost_ok = cost_ratio is not None and cost_ratio >= config.minimum_cost_reduction
    if cost_ratio is None:
        risks.append("no cost signal (all-local/zero-cost run); cost reduction cannot be quantified")
        evidence.append("cost reduction not quantifiable (zero-cost run)")
    else:
        evidence.append(f"{cost_ratio * 100:.0f}% cost reduction vs baseline")

    if cascade is not None:
        evidence.append(
            f"{cascade.final_success_rate * 100:.0f}% success after escalation ({cascade.escalation_rate * 100:.0f}% escalated)"
        )

    # Decision ladder.
    if (
        candidate.total_cases == 0
        or (candidate.successful_cases == 0 and candidate.error_cases == candidate.total_cases)
        or not candidate.evidence_sufficient
    ):
        recommendation = INSUFFICIENT_EVIDENCE
        eligible = False
        risks.extend(candidate.evidence_warnings)
    elif failed:
        eligible = False
        if (
            cascade is not None
            and cascade.final_success_rate >= max(baseline.success_rate, config.minimum_reliability or 0.0)
            and policy_pass
            and deployment_compatible
        ):
            recommendation = FIRST_STAGE_WITH_ESCALATION
        else:
            recommendation = NOT_RECOMMENDED
    elif not cost_ok:
        eligible = True
        recommendation = RECOMMENDED_WITH_CONDITIONS
        risks.append("quality/reliability acceptable but target cost reduction not demonstrated")
    else:
        eligible = True
        recommendation = RECOMMENDED

    confidence = 0.9 if candidate.total_cases >= candidate.minimum_recommended_sample_size else 0.4
    if cost_ratio is None:
        confidence -= 0.2
    confidence = max(0.1, min(1.0, confidence))

    next_step = {
        RECOMMENDED: "Pilot the candidate on a slice of production traffic and monitor quality/cost.",
        RECOMMENDED_WITH_CONDITIONS: "Confirm real-world cost with a compute-cost profile before switching.",
        FIRST_STAGE_WITH_ESCALATION: "Deploy as first stage with escalation to the baseline on failure.",
        NOT_RECOMMENDED: "Keep the baseline; revisit after addressing the failed constraints.",
        INSUFFICIENT_EVIDENCE: "Add more cases / repetitions before deciding.",
    }[recommendation]

    return ReplacementDecision(
        baseline_model=baseline.model_alias,
        candidate_model=candidate.model_alias,
        eligible=eligible,
        recommendation=recommendation,
        confidence=confidence,
        quality_delta=quality_delta,
        cost_delta_usd=cost_delta,
        cost_reduction_ratio=cost_ratio,
        latency_delta_ms=latency_delta,
        reliability_delta=reliability_delta,
        policy_pass=policy_pass,
        deployment_compatible=deployment_compatible,
        failed_constraints=failed,
        risks=risks,
        evidence=evidence,
        recommended_next_step=next_step,
    )
