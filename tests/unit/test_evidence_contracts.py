from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from model_swap_bench.errors import ConfigError
from model_swap_bench.outcomes import HumanOutcomeRecord, OutcomeLabel, aggregate_outcomes, compare_outcomes, load_outcomes_jsonl
from model_swap_bench.privacy import provider_data_preflight
from model_swap_bench.replay import ReplayTrace, build_replay_preflight, load_replay_jsonl, render_replay_jsonl, sanitize_replay
from model_swap_bench.statistics import bootstrap_mean_interval, describe, paired_comparison, percentile, wilson_interval
from model_swap_bench.telemetry import render_otel_jsonl, workflow_to_otel
from model_swap_bench.workflows import StepKind, WorkflowStep, WorkflowTrace, evaluate_workflow


def _workflow() -> WorkflowTrace:
    return WorkflowTrace(
        trace_id="trace-1",
        case_id="case-1",
        task_id="support",
        requested_model="candidate",
        response_model="candidate-local",
        provider="deterministic",
        expected_tool_sequence=["lookup", "update"],
        business_success=True,
        risk_level="low",
        steps=[
            WorkflowStep(sequence=0, kind=StepKind.USER_MESSAGE, content="help", estimated_cost_usd=Decimal("0")),
            WorkflowStep(sequence=1, kind=StepKind.TOOL_CALL, tool_name="lookup", estimated_cost_usd=Decimal("0.01")),
            WorkflowStep(
                sequence=2, kind=StepKind.TOOL_RESULT, tool_succeeded=False, error_type="unavailable", estimated_cost_usd=Decimal("0")
            ),
            WorkflowStep(sequence=3, kind=StepKind.TOOL_CALL, tool_name="update", timeout=True, estimated_cost_usd=Decimal("0.01")),
            WorkflowStep(
                sequence=4, kind=StepKind.MODEL_RESPONSE, content="retry", policy_result="allowed", estimated_cost_usd=Decimal("0.01")
            ),
            WorkflowStep(sequence=5, kind=StepKind.HUMAN_REVIEW, content="approved", estimated_cost_usd=Decimal("0")),
            WorkflowStep(
                sequence=6,
                kind=StepKind.FINAL_ANSWER,
                content="resolved",
                latency_ms=12,
                input_tokens=4,
                output_tokens=8,
                estimated_cost_usd=Decimal("0.02"),
            ),
        ],
    )


def test_statistics_are_deterministic_and_signal_small_samples() -> None:
    values = [1.0, 2.0, 3.0, 100.0]
    assert percentile(values, 50) == 2.5
    assert percentile([], 50) is None
    assert wilson_interval(8, 10) is not None
    assert wilson_interval(1, 0) is None
    assert bootstrap_mean_interval(values) == bootstrap_mean_interval(values)
    assert describe(values).outlier_count == 1
    assert describe([]).mean is None
    paired = paired_comparison([1, 2, 3], [2, 2, 1], minimum_sample_size=20)
    assert (paired.wins, paired.ties, paired.losses) == (1, 1, 1)
    assert not paired.sufficient_evidence
    with pytest.raises(ValueError, match="equal length"):
        paired_comparison([1], [1, 2])


def test_human_outcomes_use_business_success_and_decimal_cost(tmp_path: Path) -> None:
    records = [
        HumanOutcomeRecord(
            case_id="a",
            model_alias="candidate",
            label=OutcomeLabel.ACCEPTED,
            business_success=True,
            estimated_cost_usd=Decimal("0.10"),
            reviewer_id="reviewer-7",
        ),
        HumanOutcomeRecord(
            case_id="b", model_alias="candidate", label=OutcomeLabel.CORRECTED, business_success=False, estimated_cost_usd=Decimal("0.20")
        ),
        HumanOutcomeRecord(
            case_id="c", model_alias="candidate", label=OutcomeLabel.ESCALATED, business_success=True, estimated_cost_usd=Decimal("0.30")
        ),
    ]
    summary = aggregate_outcomes(records)
    assert summary.human_acceptance_rate == 0.3333
    assert summary.business_success_rate == 0.6667
    assert summary.cost_per_successful_outcome_usd == Decimal("0.30")
    assert aggregate_outcomes([]).business_success_rate is None
    comparison = compare_outcomes(records[:1], records)
    assert comparison.business_success_rate_difference == -0.3333
    assert comparison.cost_per_successful_outcome_difference_usd == Decimal("0.20")
    assert compare_outcomes([], records).human_acceptance_rate_difference is None
    with pytest.raises(ValidationError, match="pseudonymous"):
        HumanOutcomeRecord(case_id="x", model_alias="x", label=OutcomeLabel.ACCEPTED, reviewer_id="fixture@example.invalid")

    path = tmp_path / "outcomes.jsonl"
    path.write_text("\n".join(record.model_dump_json() for record in records), encoding="utf-8")
    assert len(load_outcomes_jsonl(path)) == 3
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid outcome"):
        load_outcomes_jsonl(path)


def test_workflow_evaluation_covers_tools_recovery_timeout_and_total_cost() -> None:
    trace = _workflow()
    result = evaluate_workflow(trace, step_limit=5)
    assert result.tool_selection_accuracy == 1.0
    assert result.tool_order_correct is True
    assert result.tool_failures == 1
    assert result.recovered_tool_failures == 1
    assert result.timeouts == 1 and result.timeout_recovered
    assert result.escalated and result.human_reviewed
    assert result.step_limit_exceeded
    assert result.total_estimated_cost_usd == Decimal("0.05")
    assert result.business_success is True

    repeated = WorkflowTrace(
        trace_id="loop",
        case_id="loop",
        requested_model="candidate",
        provider="fixture",
        steps=[WorkflowStep(sequence=index, kind=StepKind.MODEL_RESPONSE, content="same") for index in range(3)],
    )
    loop = evaluate_workflow(repeated)
    assert loop.loop_detected
    assert loop.total_estimated_cost_usd is None
    with pytest.raises(ValidationError, match="ascending"):
        WorkflowTrace(
            trace_id="bad",
            case_id="bad",
            requested_model="x",
            provider="x",
            steps=[WorkflowStep(sequence=1, kind=StepKind.USER_MESSAGE), WorkflowStep(sequence=0, kind=StepKind.FINAL_ANSWER)],
        )


def test_replay_sanitization_preflight_and_otel_mapping(tmp_path: Path) -> None:
    trace = ReplayTrace(
        trace_id="customer-123",
        case_id="case-123",
        task_id="task-123",
        request_messages=[{"role": "user", "content": "fixture-user@example.invalid +1 202 555 0100 sk-ABCDEFGHIJKLMNOP"}],
        provider="local",
        privacy_classification="confidential",
    )
    sanitized, findings = sanitize_replay([trace])
    rendered = render_replay_jsonl(sanitized)
    assert "fixture-user" not in rendered and "sk-ABCDEFGHIJKLMNOP" not in rendered
    assert findings["emails"] == 1 and findings["credentials_or_tokens"] == 1
    assert sanitized[0].trace_id != trace.trace_id
    assert sanitize_replay([trace]) == (sanitized, findings)

    preflight = build_replay_preflight([trace], findings, provider_mode="hosted", hosted_execution_enabled=False, redaction_applied=False)
    assert preflight.sensitive_content_found and not preflight.content_leaves_machine
    assert len(preflight.warnings) == 2
    with pytest.raises(ConfigError, match="excerpt"):
        sanitize_replay([trace], excerpt_length=100_000)
    omitted, _ = sanitize_replay([trace], omit_content=True, excerpt_length=0)
    assert omitted[0].provider == "local"
    assert omitted[0].request_messages[0]["content"] == "[content-omitted]"

    path = tmp_path / "replay.jsonl"
    path.write_text(trace.model_dump_json() + "\n", encoding="utf-8")
    assert load_replay_jsonl(path) == [trace]
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid replay"):
        load_replay_jsonl(path)

    otel = workflow_to_otel(
        _workflow(),
        dataset_id="private-support",
        dataset_digest="a" * 64,
        benchmark_run_id="run-1",
        evaluation_score=0.9,
        route_decision="candidate_model",
    )
    assert otel.attributes["gen_ai.usage.input_tokens"] == 4
    assert "modelswapbench.dataset.digest" in render_otel_jsonl([otel])
    assert render_otel_jsonl([]) == ""


def test_hosted_execution_requires_explicit_permission() -> None:
    blocked = provider_data_preflight(
        provider="hosted-provider",
        hosting_mode="hosted",
        dataset_privacy_classification="confidential",
        allow_hosted=False,
        raw_outputs_stored=True,
        telemetry_enabled=True,
    )
    assert not blocked.allowed
    assert not blocked.raw_prompts_transmitted
    assert len(blocked.warnings) == 3

    local = provider_data_preflight(
        provider="deterministic",
        hosting_mode="local",
        dataset_privacy_classification="restricted",
        allow_hosted=False,
        raw_outputs_stored=False,
    )
    assert local.allowed and not local.content_leaves_machine
