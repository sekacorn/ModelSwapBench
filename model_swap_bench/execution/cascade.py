"""Cascade execution: run a cheap/local model first, escalate failures to a stronger one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from model_swap_bench.config.models import CascadeCondition
from model_swap_bench.errors import ConfigError
from model_swap_bench.execution.context import ExecutionContext
from model_swap_bench.providers.base import build_provider
from model_swap_bench.results import BenchmarkRun, CascadeSummary, CaseResult, CaseStatus, EvalStatus
from model_swap_bench.scoring import economics

if TYPE_CHECKING:
    from model_swap_bench.execution.runner import BenchmarkRunner


def should_escalate(
    result: CaseResult,
    conditions: list[CascadeCondition],
    cfg_low_score: float,
    cfg_low_conf: float,
    escalate_tags: list[str],
    case_tags: list[str],
) -> bool:
    """Decide whether a first-stage result triggers escalation."""
    for cond in conditions:
        if cond is CascadeCondition.EVALUATOR_FAILURE and result.status is not CaseStatus.SUCCESS:
            return True
        if cond is CascadeCondition.INVALID_JSON and not result.valid_json:
            return True
        if cond is CascadeCondition.TIMEOUT and result.status is CaseStatus.TIMEOUT:
            return True
        if cond is CascadeCondition.LOW_SCORE and result.quality_score < cfg_low_score:
            return True
        if cond is CascadeCondition.POLICY_FAILURE and any(
            e.evaluator == "policy_compliance" and not e.passed and e.status is not EvalStatus.SKIPPED for e in result.evaluations
        ):
            return True
        if cond is CascadeCondition.LOW_CONFIDENCE and result.evaluations:
            if min(e.confidence for e in result.evaluations) < cfg_low_conf:
                return True
        if cond is CascadeCondition.CASE_TAG and any(t in escalate_tags for t in case_tags):
            return True
    return False


async def run_cascade(runner: BenchmarkRunner, ctx: ExecutionContext, run: BenchmarkRun) -> None:
    """Execute a cascade and populate ``run.case_results`` and ``run.cascade_summary``."""
    from model_swap_bench.execution.runner import run_case

    cascade = runner.suite.cascade
    if cascade is None:
        raise ConfigError("cascade execution requires a cascade configuration")
    first = runner.suite.model_by_alias(cascade.first_stage)
    escal = runner.suite.model_by_alias(cascade.escalation_model)
    if first is None or escal is None:
        raise ConfigError("cascade execution references an unknown model alias")

    first_provider = build_provider(first, suite_dir=runner.suite_dir, allow_hosted=runner.allow_hosted)
    escal_provider = build_provider(escal, suite_dir=runner.suite_dir, allow_hosted=runner.allow_hosted)

    total = len(runner.suite.cases)
    first_success = 0
    final_success = 0
    escalated = 0
    total_cost = 0.0
    try:
        for case in runner.suite.cases:
            first_result = await run_case(ctx, first, first_provider, case)
            run.case_results.append(first_result)
            total_cost += first_result.estimated_cost_usd
            if first_result.status is CaseStatus.SUCCESS:
                first_success += 1

            do_escalate = should_escalate(
                first_result,
                cascade.conditions,
                cascade.low_score_threshold,
                cascade.low_confidence_threshold,
                cascade.escalate_tags,
                case.tags,
            )
            if do_escalate:
                escalated += 1
                escal_result = await run_case(ctx, escal, escal_provider, case)
                escal_result.escalated = True
                run.case_results.append(escal_result)
                total_cost += escal_result.estimated_cost_usd
                final_ok = escal_result.status is CaseStatus.SUCCESS
            else:
                final_ok = first_result.status is CaseStatus.SUCCESS
            if final_ok:
                final_success += 1
    finally:
        await first_provider.aclose()
        await escal_provider.aclose()

    run.cascade_summary = CascadeSummary(
        first_stage_model=first.alias,
        escalation_model=escal.alias,
        total_cases=total,
        first_stage_success=first_success,
        escalated_cases=escalated,
        final_success=final_success,
        escalation_rate=escalated / total if total else 0.0,
        first_stage_success_rate=first_success / total if total else 0.0,
        final_success_rate=final_success / total if total else 0.0,
        total_cost_usd=total_cost,
        cost_per_success_usd=economics.cost_per_success(total_cost, final_success),
    )
