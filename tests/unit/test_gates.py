from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from model_swap_bench.errors import ConfigError
from model_swap_bench.gates import (
    GateArtifact,
    GateCaseEvidence,
    GateMetrics,
    GateStatus,
    GateThresholds,
    RiskGateThresholds,
    evaluate_gate,
    load_gate_artifact,
    load_gate_thresholds,
    render_gate,
)


def _artifact(*, candidate: bool = False, sample_size: int = 30, digest: str = "a" * 64) -> GateArtifact:
    value = 0.92 if not candidate else 0.90
    return GateArtifact(
        model="candidate" if candidate else "baseline",
        run_id="candidate-run" if candidate else "baseline-run",
        dataset_id="support",
        dataset_digest=digest,
        run_digest=("c" if candidate else "b") * 64,
        sample_size=sample_size,
        metrics=GateMetrics(
            quality=value,
            success_rate=value,
            reliability=0.95,
            valid_json_rate=1.0,
            policy_pass_rate=1.0,
            tool_call_accuracy=0.95,
            citation_correctness=0.95,
            p95_latency_ms=90 if candidate else 100,
            estimated_cost_usd=Decimal("1.00") if candidate else Decimal("2.00"),
            cost_per_successful_outcome_usd=Decimal("0.10"),
            human_review_rate=0.05,
            escalation_rate=0.02,
            error_rate=0.01,
            timeout_rate=0.0,
            human_acceptance_rate=0.90,
            business_success_rate=0.90,
        ),
        cases=[
            GateCaseEvidence(
                case_id=f"case-{index}", risk_level="high", quality=value, success=True, policy_pass=True, business_success=True
            )
            for index in range(sample_size)
        ],
        pricing_source="operator fixture",
        pricing_status="current",
    )


def _thresholds() -> GateThresholds:
    return GateThresholds(
        minimum_sample_size=20,
        minimum_quality=0.85,
        minimum_success_rate=0.85,
        minimum_reliability=0.90,
        minimum_valid_json_rate=0.90,
        minimum_policy_pass_rate=0.95,
        minimum_tool_call_accuracy=0.90,
        minimum_citation_correctness=0.90,
        maximum_p95_latency_ms=120,
        maximum_latency_increase_ratio=0.10,
        maximum_estimated_cost_usd=Decimal("1.50"),
        minimum_cost_reduction_ratio=0.25,
        maximum_cost_per_successful_outcome_usd=Decimal("0.20"),
        maximum_human_review_rate=0.10,
        maximum_escalation_rate=0.10,
        maximum_error_rate=0.05,
        maximum_timeout_rate=0.05,
        minimum_human_acceptance_rate=0.80,
        minimum_business_success_rate=0.80,
        risk_specific={
            "high": RiskGateThresholds(
                minimum_quality=0.85, minimum_success_rate=0.85, minimum_policy_pass_rate=1.0, minimum_business_success_rate=0.80
            )
        },
    )


def test_gate_passes_and_renders_all_machine_formats() -> None:
    result = evaluate_gate(_artifact(), _artifact(candidate=True), _thresholds())
    assert result.status is GateStatus.PASS
    assert result.exit_code == 0
    for fmt in ("console", "json", "markdown", "github", "junit"):
        rendered = render_gate(result, fmt)
        assert rendered
    assert "testsuite" in render_gate(result, "junit")
    with pytest.raises(ConfigError, match="format"):
        render_gate(result, "html")


def test_gate_distinguishes_regression_and_insufficient_evidence() -> None:
    weak = _artifact(candidate=True)
    weak.metrics.quality = 0.50
    regression = evaluate_gate(_artifact(), weak, _thresholds())
    assert regression.status is GateStatus.REGRESSION
    assert regression.exit_code == 1

    sparse = _artifact(candidate=True, sample_size=2)
    sparse.metrics.quality = None
    insufficient = evaluate_gate(
        _artifact(), sparse, GateThresholds(minimum_sample_size=20, maximum_quality_drop=None, maximum_success_rate_drop=None)
    )
    assert insufficient.status is GateStatus.INSUFFICIENT_EVIDENCE
    assert insufficient.exit_code == 4

    mismatch = evaluate_gate(_artifact(), _artifact(candidate=True, digest="d" * 64), GateThresholds())
    assert mismatch.status is GateStatus.REGRESSION


def test_gate_missing_risk_evidence_and_unknown_pricing_warn() -> None:
    candidate = _artifact(candidate=True)
    candidate.cases = []
    candidate.pricing_status = "unknown"
    result = evaluate_gate(
        _artifact(),
        candidate,
        GateThresholds(risk_specific={"regulated": RiskGateThresholds(minimum_quality=0.9)}),
    )
    assert result.status is GateStatus.INSUFFICIENT_EVIDENCE
    assert any("pricing" in warning for warning in result.warnings)


def test_gate_artifact_and_threshold_loaders(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text(_artifact().model_dump_json(), encoding="utf-8")
    assert load_gate_artifact(artifact_path).model == "baseline"
    assert load_gate_thresholds(None).minimum_sample_size == 20

    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"minimum_sample_size": 25}), encoding="utf-8")
    assert load_gate_thresholds(thresholds_path).minimum_sample_size == 25
    thresholds_path.write_text(json.dumps({"minimum_sample_size": 0}), encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid gate thresholds"):
        load_gate_thresholds(thresholds_path)
    artifact_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid gate artifact"):
        load_gate_artifact(artifact_path)
