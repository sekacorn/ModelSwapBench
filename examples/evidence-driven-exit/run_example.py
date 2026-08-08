"""Generate a complete, local-only vendor-exit evidence bundle."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from model_swap_bench._version import __version__
from model_swap_bench.datasets.io import dataset_digest, write_dataset
from model_swap_bench.datasets.models import DatasetCase, DatasetMessage, EvaluationDataset
from model_swap_bench.gates import GateArtifact, GateCaseEvidence, GateMetrics, GateThresholds, evaluate_gate, render_gate_json
from model_swap_bench.outcomes import HumanOutcomeRecord, OutcomeLabel, aggregate_outcomes
from model_swap_bench.portable import pretty_json
from model_swap_bench.replay import ReplayTrace, build_replay_preflight, render_replay_jsonl, sanitize_replay
from model_swap_bench.reports.route_plan import (
    build_model_routing_plan,
    build_route_aimeter_export,
    build_route_audit_events,
    render_model_routing_plan_json,
    render_model_routing_plan_markdown,
    render_route_aimeter_export_json,
    render_route_audit_events_jsonl,
)
from model_swap_bench.telemetry import render_otel_jsonl, workflow_to_otel
from model_swap_bench.workflows import StepKind, WorkflowStep, WorkflowTrace, evaluate_workflow


def _write(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def main(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        DatasetCase(
            case_id=f"support-{index:02d}",
            input_messages=[DatasetMessage(role="user", content=f"Example-only account support request {index}.")],
            expected_output={"route": "account_help"},
            expected_tool_calls=[],
            expected_policy_result="allowed",
            risk_level="low" if index < 20 else "high",
            workload="customer-support",
            privacy_classification="internal",
            human_outcome_label="accepted" if index != 23 else "escalated",
        )
        for index in range(24)
    ]
    dataset = EvaluationDataset(
        dataset_id="private-customer-support",
        name="Private customer-support replacement evidence",
        privacy_classification="internal",
        cases=cases,
    )
    digest = dataset_digest(dataset)
    write_dataset(dataset, output_dir / "dataset.jsonl")

    trace = WorkflowTrace(
        trace_id="support-workflow-01",
        case_id="support-01",
        task_id="account-help",
        requested_model="candidate-fixture",
        response_model="candidate-fixture",
        provider="deterministic",
        expected_tool_sequence=["account_lookup"],
        business_success=True,
        risk_level="low",
        privacy_classification="internal",
        steps=[
            WorkflowStep(sequence=0, kind=StepKind.USER_MESSAGE, content="Example-only account request.", estimated_cost_usd=Decimal("0")),
            WorkflowStep(
                sequence=1,
                kind=StepKind.TOOL_CALL,
                tool_name="account_lookup",
                tool_arguments={"account_ref": "fixture-01"},
                estimated_cost_usd=Decimal("0.001"),
            ),
            WorkflowStep(
                sequence=2,
                kind=StepKind.TOOL_RESULT,
                content="Example-only account status.",
                tool_succeeded=True,
                estimated_cost_usd=Decimal("0"),
            ),
            WorkflowStep(
                sequence=3,
                kind=StepKind.FINAL_ANSWER,
                content="The example request is resolved.",
                policy_result="allowed",
                latency_ms=18,
                input_tokens=20,
                output_tokens=12,
                estimated_cost_usd=Decimal("0.002"),
            ),
        ],
    )
    _write(output_dir / "workflow.jsonl", trace.model_dump_json() + "\n")
    _write(output_dir / "workflow-evaluation.json", pretty_json(evaluate_workflow(trace).model_dump(mode="json")))

    labels = [
        HumanOutcomeRecord(
            case_id=case.case_id,
            model_alias="candidate-fixture",
            label=OutcomeLabel.ACCEPTED,
            business_success=True,
            estimated_cost_usd=Decimal("0.003"),
        )
        for case in cases
    ]
    _write(output_dir / "outcomes.jsonl", "\n".join(record.model_dump_json() for record in labels) + "\n")
    _write(output_dir / "outcome-summary.json", pretty_json(aggregate_outcomes(labels).model_dump(mode="json")))

    def artifact(model: str, *, quality: float, cost: str) -> GateArtifact:
        return GateArtifact(
            model=model,
            run_id=f"{model}-run",
            dataset_id=dataset.dataset_id,
            dataset_digest=digest,
            run_digest=("a" if model == "baseline-fixture" else "b") * 64,
            sample_size=len(cases),
            metrics=GateMetrics(
                quality=quality,
                success_rate=0.96,
                reliability=0.96,
                policy_pass_rate=1.0,
                tool_call_accuracy=1.0,
                p95_latency_ms=20 if model == "baseline-fixture" else 18,
                estimated_cost_usd=Decimal(cost),
                business_success_rate=1.0,
            ),
            cases=[
                GateCaseEvidence(
                    case_id=case.case_id,
                    risk_level=case.risk_level.value,
                    quality=quality,
                    success=True,
                    policy_pass=True,
                    business_success=True,
                )
                for case in cases
            ],
            pricing_source="example operator estimate",
            pricing_status="estimated",
            reproducibility={"modelswapbench_version": __version__, "dataset_digest": digest},
        )

    baseline = artifact("baseline-fixture", quality=0.94, cost="1.20")
    candidate = artifact("candidate-fixture", quality=0.91, cost="0.30")
    _write(output_dir / "baseline.json", baseline.model_dump_json(indent=2))
    _write(output_dir / "candidate.json", candidate.model_dump_json(indent=2))
    gate = evaluate_gate(
        baseline, candidate, GateThresholds(minimum_sample_size=20, minimum_quality=0.90, minimum_cost_reduction_ratio=0.50)
    )
    _write(output_dir / "gate-result.json", render_gate_json(gate))

    route_input = {
        "run_id": "evidence-driven-example",
        "generated_at": "2026-01-01T00:00:00Z",
        "workload": "Customer support",
        "tasks": [
            {
                "task_id": "account-help",
                "category": "support",
                "risk_level": "low",
                "baseline_score": "0.94",
                "candidate_score": "0.91",
                "baseline_cost": "1.20",
                "candidate_cost": "0.30",
                "baseline_latency": "20",
                "candidate_latency": "18",
                "candidate_policy_pass_rate": "1",
                "candidate_business_success_rate": "1",
                "sample_size": 24,
                "dataset_digest": digest,
                "run_digest": "b" * 64,
            },
            {
                "task_id": "security-escalation",
                "category": "security-sensitive",
                "risk_level": "high",
                "baseline_score": "0.95",
                "candidate_score": "0.92",
                "baseline_cost": "1.20",
                "candidate_cost": "0.30",
                "baseline_latency": "20",
                "candidate_latency": "18",
                "candidate_policy_pass_rate": "1",
                "sample_size": 24,
                "required_human_review": True,
                "dataset_digest": digest,
                "run_digest": "b" * 64,
            },
        ],
    }
    route_input_path = output_dir / "route-input.json"
    _write(route_input_path, pretty_json(route_input))
    plan = build_model_routing_plan(input_path=route_input_path, baseline_model="baseline-fixture", candidate_model="candidate-fixture")
    _write(output_dir / "vendor-exit-plan.md", render_model_routing_plan_markdown(plan))
    _write(output_dir / "vendor-exit-plan.json", render_model_routing_plan_json(plan))
    _write(output_dir / "aimeter-style.json", render_route_aimeter_export_json(build_route_aimeter_export(plan)))
    _write(output_dir / "aiauditlog-style.jsonl", render_route_audit_events_jsonl(build_route_audit_events(plan)))

    otel = workflow_to_otel(
        trace,
        dataset_id=dataset.dataset_id,
        dataset_digest=digest,
        benchmark_run_id="candidate-run",
        evaluation_score=0.91,
        route_decision="candidate_model",
    )
    _write(output_dir / "otel.jsonl", render_otel_jsonl([otel]))
    replay = ReplayTrace(
        trace_id=trace.trace_id,
        case_id=trace.case_id,
        task_id=trace.task_id,
        request_messages=[{"role": "user", "content": "Example-only account request."}],
        response_messages=[{"role": "assistant", "content": "Resolved."}],
        tool_calls=[{"name": "account_lookup"}],
        provider="deterministic",
        privacy_classification="internal",
    )
    sanitized, findings = sanitize_replay([replay])
    _write(output_dir / "sanitized-replay.jsonl", render_replay_jsonl(sanitized))
    preflight = build_replay_preflight([replay], findings, provider_mode="local", hosted_execution_enabled=False, redaction_applied=True)
    _write(output_dir / "replay-preflight.json", pretty_json(preflight.model_dump(mode="json")))


if __name__ == "__main__":
    main(Path("evidence-output"))
