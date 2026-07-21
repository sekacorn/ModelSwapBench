from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from model_swap_bench.cli.app import app
from model_swap_bench.errors import ConfigError
from model_swap_bench.reports.route_plan import (
    RouteDecision,
    RoutingThresholds,
    TaskRoutingInput,
    build_model_routing_plan,
    build_route_aimeter_export,
    build_route_audit_events,
    cost_reduction_pct,
    decide_task_route,
    load_route_plan_input,
    render_model_routing_plan_json,
    render_model_routing_plan_markdown,
    render_route_aimeter_export_json,
    render_route_audit_events_jsonl,
)

runner = CliRunner()


def _task(
    task_id: str,
    *,
    risk: str = "low",
    category: str = "general",
    baseline_score: str | None = "0.90",
    candidate_score: str | None = "0.84",
    baseline_cost: str | None = "1.00",
    candidate_cost: str | None = "0.25",
    baseline_latency: str | None = "1000",
    candidate_latency: str | None = "900",
    policy_flags: list[str] | None = None,
    failure_flags: list[str] | None = None,
) -> TaskRoutingInput:
    return TaskRoutingInput(
        task_id=task_id,
        category=category,
        risk_level=risk,
        baseline_score=None if baseline_score is None else Decimal(baseline_score),
        candidate_score=None if candidate_score is None else Decimal(candidate_score),
        baseline_cost=None if baseline_cost is None else Decimal(baseline_cost),
        candidate_cost=None if candidate_cost is None else Decimal(candidate_cost),
        baseline_latency=None if baseline_latency is None else Decimal(baseline_latency),
        candidate_latency=None if candidate_latency is None else Decimal(candidate_latency),
        policy_flags=policy_flags or [],
        failure_flags=failure_flags or [],
    )


def test_low_risk_passing_task_routes_to_candidate_model() -> None:
    decision = decide_task_route(_task("password-reset"), RoutingThresholds())
    assert decision.route is RouteDecision.CANDIDATE_MODEL


def test_high_risk_passing_task_routes_to_human_review() -> None:
    decision = decide_task_route(_task("security-concern", risk="high", policy_flags=["security-sensitive"]), RoutingThresholds())
    assert decision.route is RouteDecision.HUMAN_REVIEW


def test_workload_risk_profile_changes_candidate_eligible_route() -> None:
    task = _task("routine")
    assert decide_task_route(task, RoutingThresholds(), risk_profile="high").route is RouteDecision.HUMAN_REVIEW
    assert decide_task_route(task, RoutingThresholds(), risk_profile="regulated").route is RouteDecision.BLOCKED_OR_ESCALATE


def test_unknown_risk_requires_review_and_category_variants_escalate() -> None:
    assert decide_task_route(_task("unknown", risk="unknown"), RoutingThresholds()).route is RouteDecision.HUMAN_REVIEW
    for category in ("legal_advice", "security-incident", "legal_medical_financial"):
        assert decide_task_route(_task(category, category=category), RoutingThresholds()).route is RouteDecision.BLOCKED_OR_ESCALATE


def test_failing_quality_routes_to_baseline_model() -> None:
    decision = decide_task_route(_task("weak", candidate_score="0.60"), RoutingThresholds())
    assert decision.route is RouteDecision.BASELINE_MODEL


def test_legal_medical_financial_tasks_escalate() -> None:
    for category in ("legal", "medical", "financial"):
        decision = decide_task_route(_task(category, risk="high", category=category), RoutingThresholds())
        assert decision.route is RouteDecision.BLOCKED_OR_ESCALATE


def test_missing_cost_is_unknown_not_zero() -> None:
    decision = decide_task_route(_task("unknown-cost", baseline_cost=None), RoutingThresholds())
    assert decision.cost_reduction_pct is None
    assert "missing pricing was not treated as zero" in " ".join(decision.warnings)
    assert cost_reduction_pct(None, Decimal("0.25")) is None


@pytest.mark.parametrize(
    "field", ["baseline_score", "candidate_score", "baseline_cost", "candidate_cost", "baseline_latency", "candidate_latency"]
)
def test_invalid_metrics_are_rejected(field: str) -> None:
    payload = _task("invalid").model_dump(mode="json")
    payload[field] = "-1"
    with pytest.raises(ValueError, match="finite and non-negative"):
        TaskRoutingInput.model_validate(payload)


@pytest.mark.parametrize("value", ["1e1000000", "1e-1000000", "0." + ("1" * 51)])
def test_pathological_decimal_values_are_rejected(value: str) -> None:
    payload = _task("invalid").model_dump(mode="json")
    payload["candidate_cost"] = value
    with pytest.raises(ValueError):
        TaskRoutingInput.model_validate(payload)


def test_duplicate_keys_and_task_ids_are_rejected(tmp_path: Path) -> None:
    duplicate_key = tmp_path / "duplicate-key.json"
    duplicate_key.write_text('{"tasks": [], "tasks": []}', encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate key"):
        load_route_plan_input(duplicate_key)

    duplicate_id = tmp_path / "duplicate-id.json"
    duplicate_id.write_text(
        json.dumps({"tasks": [_task("same").model_dump(mode="json"), _task("same").model_dump(mode="json")]}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="duplicate route-plan task_id"):
        load_route_plan_input(duplicate_id)


def test_markdown_untrusted_fields_cannot_create_rows_or_html(tmp_path: Path) -> None:
    input_path = tmp_path / "route.json"
    input_path.write_text(
        json.dumps(
            {"workload": "Support\n# injected", "tasks": [_task("task|row<script>", category="general\n| fake").model_dump(mode="json")]}
        ),
        encoding="utf-8",
    )
    markdown = render_model_routing_plan_markdown(
        build_model_routing_plan(input_path=input_path, baseline_model="base`line", candidate_model="candidate")
    )
    assert "<script>" not in markdown
    assert "\n# injected" not in markdown
    assert "task|row" not in markdown
    assert "general\n| fake" not in markdown
    assert "&#124;" in markdown


def test_blended_savings_unknown_when_cost_data_insufficient(tmp_path: Path) -> None:
    input_path = tmp_path / "route.json"
    input_path.write_text(
        json.dumps(
            {
                "workload": "Support",
                "tasks": [
                    _task("candidate").model_dump(mode="json"),
                    _task("missing", baseline_cost=None, category="financial", risk="high").model_dump(mode="json"),
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = build_model_routing_plan(input_path=input_path, baseline_model="baseline", candidate_model="candidate")
    assert plan.summary.estimated_blended_savings_pct is None
    assert plan.summary.baseline_total_estimated_cost is None


def test_markdown_json_aimeter_and_audit_renderers_parse(tmp_path: Path) -> None:
    input_path = tmp_path / "route.json"
    input_path.write_text(
        json.dumps(
            {
                "workload": "Support",
                "tasks": [
                    _task("candidate").model_dump(mode="json"),
                    _task("review", risk="high", policy_flags=["customer-facing"]).model_dump(mode="json"),
                    _task("baseline", candidate_score="0.60").model_dump(mode="json"),
                    _task("blocked", category="legal", risk="high").model_dump(mode="json"),
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = build_model_routing_plan(
        input_path=input_path,
        baseline_model="openai:gpt-4o",
        candidate_model="ollama:qwen2.5:3b",
        run_id="route-test",
    )
    markdown = render_model_routing_plan_markdown(plan)
    assert "# Model Routing Plan" in markdown
    payload = json.loads(render_model_routing_plan_json(plan))
    assert payload["summary"]["total_tasks"] == 4
    aimeter = json.loads(render_route_aimeter_export_json(build_route_aimeter_export(plan)))
    assert aimeter["cost"]["baseline_total_estimated_cost"]["known"] is True
    events = [json.loads(line) for line in render_route_audit_events_jsonl(build_route_audit_events(plan)).splitlines()]
    assert {event["event_type"] for event in events} >= {
        "route_plan_started",
        "route_plan_input_loaded",
        "routing_thresholds_evaluated",
        "task_route_decision_recorded",
        "route_plan_generated",
    }
    assert "compliance" not in json.dumps(events).lower()
    assert "non-repudiation" not in json.dumps(events).lower()

    previous_hash = None
    for event in events:
        assert event["previous_hash"] == previous_hash
        expected = event["event_hash"]
        event_for_hash = dict(event)
        event_for_hash.pop("event_hash")
        event_for_hash["integrity"] = dict(event_for_hash["integrity"])
        event_for_hash["integrity"].pop("event_digest")
        canonical = json.dumps(event_for_hash, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected
        previous_hash = expected


def test_cli_route_plan_help_and_outputs(tmp_path: Path) -> None:
    help_result = runner.invoke(app, ["route-plan", "--help"])
    assert help_result.exit_code == 0

    input_path = tmp_path / "route.json"
    output_path = tmp_path / "route.md"
    json_path = tmp_path / "route.json.out"
    aimeter_path = tmp_path / "aimeter.json"
    audit_path = tmp_path / "audit.jsonl"
    input_path.write_text(
        json.dumps(
            {"tasks": [_task("candidate").model_dump(mode="json"), _task("legal", category="legal", risk="high").model_dump(mode="json")]}
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "route-plan",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--baseline",
            "openai:gpt-4o",
            "--candidate",
            "ollama:qwen2.5:3b",
            "--export-json",
            str(json_path),
            "--export-aimeter",
            str(aimeter_path),
            "--export-auditlog",
            str(audit_path),
            "--run-id",
            "cli-route",
        ],
    )
    assert result.exit_code == 0
    assert "Model Routing Plan" in output_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["run_id"] == "cli-route"
    assert json.loads(aimeter_path.read_text(encoding="utf-8"))["routes"]["candidate_model"] == 1
    assert all(json.loads(line)["run_id"] == "cli-route" for line in audit_path.read_text(encoding="utf-8").splitlines())
    assert "@" not in output_path.read_text(encoding="utf-8")


def test_cli_rejects_input_overwrite_and_export_collisions(tmp_path: Path) -> None:
    input_path = tmp_path / "route.json"
    input_path.write_text(json.dumps({"tasks": [_task("candidate").model_dump(mode="json")]}), encoding="utf-8")
    overwrite = runner.invoke(app, ["route-plan", "--input", str(input_path), "--output", str(input_path)])
    assert overwrite.exit_code == 2
    assert "must not overwrite" in overwrite.output

    shared = tmp_path / "shared.json"
    collision = runner.invoke(
        app,
        [
            "route-plan",
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "route.md"),
            "--export-json",
            str(shared),
            "--export-aimeter",
            str(shared),
        ],
    )
    assert collision.exit_code == 2
    assert "collides" in collision.output


def test_cli_reports_schema_and_threshold_errors_as_invalid_input(tmp_path: Path) -> None:
    invalid_schema = tmp_path / "invalid.json"
    invalid_schema.write_text('{"tasks": [{"task_id": "bad", "baseline_cost": -1}]}', encoding="utf-8")
    schema_result = runner.invoke(
        app,
        ["route-plan", "--input", str(invalid_schema), "--output", str(tmp_path / "route.md")],
    )
    assert schema_result.exit_code == 2
    assert "invalid route-plan task" in schema_result.output
    assert "internal error" not in schema_result.output

    valid_input = tmp_path / "valid.json"
    valid_input.write_text(json.dumps({"tasks": [_task("candidate").model_dump(mode="json")]}), encoding="utf-8")
    threshold_result = runner.invoke(
        app,
        [
            "route-plan",
            "--input",
            str(valid_input),
            "--output",
            str(tmp_path / "route.md"),
            "--min-cost-reduction",
            "-1",
        ],
    )
    assert threshold_result.exit_code == 2
    assert "thresholds must be finite" in threshold_result.output
