"""Aggregate per-case results into per-model summaries and check constraints."""

from __future__ import annotations

from collections.abc import Sequence

from model_swap_bench.config.models import Constraints, ModelCandidate
from model_swap_bench.results import CaseResult, CaseStatus, ConstraintResult, EvalStatus, ModelSummary
from model_swap_bench.scoring import economics, metrics
from model_swap_bench.statistics import bootstrap_mean_interval, describe, wilson_interval

MINIMUM_RECOMMENDED_SAMPLE_SIZE = 20


def _has_eval(result: CaseResult, evaluator: str) -> bool:
    return any(e.evaluator == evaluator and e.status is not EvalStatus.SKIPPED for e in result.evaluations)


def _eval_passed(result: CaseResult, evaluator: str) -> bool:
    return all(e.passed for e in result.evaluations if e.evaluator == evaluator and e.status is not EvalStatus.SKIPPED)


def build_model_summary(
    candidate: ModelCandidate,
    results: Sequence[CaseResult],
) -> ModelSummary:
    """Compute aggregate metrics for one model across its case results."""
    total = len(results)
    successful = [r for r in results if r.status is CaseStatus.SUCCESS]
    failed = [r for r in results if r.status is CaseStatus.FAILED]
    errored = [r for r in results if r.status is CaseStatus.ERROR]
    timed_out = [r for r in results if r.status is CaseStatus.TIMEOUT]
    executed = [r for r in results if r.status in (CaseStatus.SUCCESS, CaseStatus.FAILED)]

    latencies = [r.latency_ms for r in executed]
    total_cost = sum(r.estimated_cost_usd for r in results)

    json_cases = [r for r in executed if _has_eval(r, "json_parse") or _has_eval(r, "json_schema")]
    valid_json = [r for r in json_cases if r.valid_json]
    policy_cases = [r for r in results if _has_eval(r, "policy_compliance")]
    policy_pass = [r for r in policy_cases if _eval_passed(r, "policy_compliance")]
    tool_cases = [r for r in results if _has_eval(r, "tool_selection")]
    tool_pass = [r for r in tool_cases if _eval_passed(r, "tool_selection")]

    quality_values = [r.quality_score for r in executed]
    quality = metrics.mean(quality_values) if executed else 0.0
    evidence_warnings: list[str] = []
    if total < MINIMUM_RECOMMENDED_SAMPLE_SIZE:
        evidence_warnings.append(f"insufficient evidence: {total} cases; at least {MINIMUM_RECOMMENDED_SAMPLE_SIZE} are recommended")

    return ModelSummary(
        model_alias=candidate.alias,
        provider=candidate.provider.value,
        deployment=candidate.deployment.value,
        total_cases=total,
        successful_cases=len(successful),
        failed_cases=len(failed),
        error_cases=len(errored),
        timeout_cases=len(timed_out),
        success_rate=metrics.rate(len(successful), total),
        quality_score=quality,
        valid_json_rate=metrics.rate(len(valid_json), len(json_cases)) if json_cases else 1.0,
        policy_pass_rate=metrics.rate(len(policy_pass), len(policy_cases)) if policy_cases else 1.0,
        tool_accuracy=metrics.rate(len(tool_pass), len(tool_cases)) if tool_cases else None,
        avg_latency_ms=metrics.mean(latencies),
        median_latency_ms=metrics.median(latencies),
        p90_latency_ms=metrics.percentile(latencies, 90),
        p95_latency_ms=metrics.percentile(latencies, 95),
        total_cost_usd=total_cost,
        cost_per_success_usd=economics.cost_per_success(total_cost, len(successful)),
        timeout_rate=metrics.rate(len(timed_out), total),
        retry_rate=metrics.rate(sum(1 for r in results if r.retries > 0), total),
        escalation_rate=metrics.rate(sum(1 for r in results if r.escalated), total),
        error_rate=metrics.rate(len(errored), total),
        success_rate_confidence_interval=wilson_interval(len(successful), total),
        quality_confidence_interval=bootstrap_mean_interval(quality_values),
        latency_distribution=describe(latencies),
        quality_distribution=describe(quality_values),
        minimum_recommended_sample_size=MINIMUM_RECOMMENDED_SAMPLE_SIZE,
        evidence_sufficient=total >= MINIMUM_RECOMMENDED_SAMPLE_SIZE,
        evidence_warnings=evidence_warnings,
    )


def check_constraints(summary: ModelSummary, constraints: Constraints) -> list[ConstraintResult]:
    """Evaluate suite-level constraints against a model summary."""
    checks: list[ConstraintResult] = []

    def add(name: str, passed: bool, threshold: float | bool | None, actual: float | bool | None, detail: str) -> None:
        checks.append(ConstraintResult(name=name, passed=passed, threshold=threshold, actual=actual, detail=detail))

    if constraints.minimum_success_rate is not None:
        ok = summary.success_rate >= constraints.minimum_success_rate
        add("minimum_success_rate", ok, constraints.minimum_success_rate, round(summary.success_rate, 4), "")
    if constraints.maximum_p95_latency_ms is not None:
        ok = summary.p95_latency_ms <= constraints.maximum_p95_latency_ms
        add("maximum_p95_latency_ms", ok, constraints.maximum_p95_latency_ms, round(summary.p95_latency_ms, 1), "")
    if constraints.maximum_cost_per_success_usd is not None:
        cps = summary.cost_per_success_usd
        ok = cps is not None and cps <= constraints.maximum_cost_per_success_usd
        detail = "" if cps is not None else "no successful cases"
        add("maximum_cost_per_success_usd", ok, constraints.maximum_cost_per_success_usd, cps, detail)
    if constraints.require_valid_json_rate is not None:
        ok = summary.valid_json_rate >= constraints.require_valid_json_rate
        add("require_valid_json_rate", ok, constraints.require_valid_json_rate, round(summary.valid_json_rate, 4), "")
    if constraints.require_policy_pass:
        ok = summary.policy_pass_rate >= 1.0
        add("require_policy_pass", ok, True, round(summary.policy_pass_rate, 4), "")
    if constraints.minimum_tool_accuracy is not None and summary.tool_accuracy is not None:
        ok = summary.tool_accuracy >= constraints.minimum_tool_accuracy
        add("minimum_tool_accuracy", ok, constraints.minimum_tool_accuracy, round(summary.tool_accuracy, 4), "")
    if constraints.maximum_timeout_rate is not None:
        ok = summary.timeout_rate <= constraints.maximum_timeout_rate
        add("maximum_timeout_rate", ok, constraints.maximum_timeout_rate, round(summary.timeout_rate, 4), "")
    return checks
