from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from model_swap_bench.cli.app import app
from model_swap_bench.errors import ConfigError
from model_swap_bench.reports.exit_report import (
    BenchmarkSummary,
    ExitDecision,
    ExitReportThresholds,
    ModelIdentity,
    build_exit_report,
    cost_reduction_pct,
    decide_exit,
    load_exit_summaries,
    parse_identity,
    quality_retention_pct,
    render_exit_report_json,
    render_exit_report_markdown,
    select_summary,
)

runner = CliRunner()


def _summary(
    label: str,
    *,
    score: str | None = "0.90",
    cost: str | None = "10.00",
    latency: str | None = "1000",
    samples: int = 20,
    failures: int = 0,
) -> BenchmarkSummary:
    provider, model = label.split(":", 1)
    return BenchmarkSummary(
        model=ModelIdentity(provider=provider, model=model, label=label),
        score=None if score is None else Decimal(score),
        average_latency_ms=None if latency is None else Decimal(latency),
        estimated_cost_usd=None if cost is None else Decimal(cost),
        sample_count=samples,
        failure_count=failures,
    )


def test_report_generation_contains_markdown_sections(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "workload": "Customer support",
                "summaries": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "score": "0.92",
                        "average_latency_ms": "1200",
                        "estimated_cost_usd": "20.00",
                        "sample_count": 10,
                        "failure_count": 0,
                    },
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:3b",
                        "score": "0.84",
                        "average_latency_ms": "900",
                        "estimated_cost_usd": "4.00",
                        "sample_count": 10,
                        "failure_count": 1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    report = build_exit_report(input_path=path, baseline_ref="openai:gpt-4o", candidate_ref="ollama:qwen2.5:3b")
    markdown = render_exit_report_markdown(report)
    for section in (
        "# AI Vendor Exit Report",
        "## Executive Summary",
        "## Models Compared",
        "## Decision",
        "## Quality",
        "## Cost",
        "## Latency",
        "## Risk",
        "## Recommendation",
        "## Limitations",
        "## Reproducibility",
    ):
        assert section in markdown


def test_quality_retention_calculation_and_zero_baseline() -> None:
    assert quality_retention_pct(Decimal("0.80"), Decimal("0.60")) == Decimal("75.00")
    assert quality_retention_pct(Decimal("0"), Decimal("0.60")) is None
    assert parse_identity("gpt-4o").provider == "unknown"


def test_cost_reduction_uses_decimal_and_missing_cost_unknown() -> None:
    reduction = cost_reduction_pct(Decimal("10.00"), Decimal("7.50"))
    assert reduction == Decimal("25.00")
    assert cost_reduction_pct(None, Decimal("1.00")) is None


def test_decision_acceptable() -> None:
    decision = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("ollama:qwen2.5:3b", score="0.80", cost="4.00", latency="900"),
        ExitReportThresholds(),
        risk_profile="low",
    )
    assert decision.decision is ExitDecision.ACCEPTABLE


def test_decision_acceptable_with_human_review() -> None:
    decision = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("local:approved", score="0.86", cost="3.00", latency="1000"),
        ExitReportThresholds(),
        risk_profile="regulated",
    )
    assert decision.decision is ExitDecision.HUMAN_REVIEW


def test_decision_not_recommended() -> None:
    decision = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("local:weak", score="0.50", cost="1.00", latency="1000"),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert decision.decision is ExitDecision.NOT_RECOMMENDED


def test_decision_not_recommended_for_latency_failure_and_failure_rate() -> None:
    slow = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("local:slow", score="0.90", cost="5.00", latency="2000"),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert slow.decision is ExitDecision.NOT_RECOMMENDED

    flaky = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("local:flaky", score="0.90", cost="5.00", latency="900", failures=8),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert flaky.decision is ExitDecision.NOT_RECOMMENDED


def test_decision_insufficient_evidence_for_missing_cost_and_small_sample() -> None:
    missing_cost = decide_exit(
        _summary("openai:gpt-4o", score="0.90", cost="10.00", latency="1000"),
        _summary("local:unknown", score="0.85", cost=None, latency="1000"),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert missing_cost.decision is ExitDecision.INSUFFICIENT
    assert missing_cost.cost_reduction_pct is None

    small_sample = decide_exit(
        _summary("openai:gpt-4o", samples=2),
        _summary("local:small", samples=2),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert small_sample.decision is ExitDecision.INSUFFICIENT

    missing_score = decide_exit(
        _summary("openai:gpt-4o", score=None),
        _summary("local:unknown", score="0.85"),
        ExitReportThresholds(),
        risk_profile="medium",
    )
    assert missing_score.decision is ExitDecision.INSUFFICIENT


def test_jsonl_and_run_summary_inputs(tmp_path: Path) -> None:
    jsonl = tmp_path / "rows.jsonl"
    jsonl.write_text(
        "\n".join(
            [
                '{"provider":"openai","model":"gpt-4o","score":"0.90","latency_ms":"1000","estimated_cost_usd":"1.00"}',
                '{"provider":"openai","model":"gpt-4o","score":"0.80","latency_ms":"1100","estimated_cost_usd":"1.50","status":"failed"}',
                '{"provider":"ollama","model":"qwen2.5:3b","score":"0.85","latency_ms":"700","estimated_cost_usd":"0.20"}',
            ]
        ),
        encoding="utf-8",
    )
    workload, summaries = load_exit_summaries(jsonl)
    assert workload is None
    baseline = select_summary(summaries, "openai:gpt-4o")
    assert baseline.sample_count == 2
    assert baseline.failure_count == 1
    assert baseline.estimated_cost_usd == Decimal("2.50")

    run_json = tmp_path / "run.json"
    run_json.write_text(
        json.dumps(
            {
                "suite_name": "exported",
                "model_summaries": [
                    {
                        "model_alias": "baseline",
                        "provider": "deterministic",
                        "quality_score": 0.9,
                        "avg_latency_ms": 100,
                        "total_cost_usd": 1,
                        "total_cases": 5,
                        "failed_cases": 1,
                        "error_cases": 0,
                        "timeout_cases": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _workload, run_summaries = load_exit_summaries(run_json)
    assert run_summaries[0].model.display_name == "baseline"


def test_error_paths_and_json_renderer(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_exit_summaries(tmp_path / "missing.json")

    bad = tmp_path / "bad.json"
    bad.write_text('{"summaries": {}}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_exit_summaries(bad)

    summaries = [_summary("openai:gpt-4o")]
    with pytest.raises(ConfigError):
        select_summary(summaries, "missing:model")

    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "summaries": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "score": "0.90",
                        "average_latency_ms": "1000",
                        "estimated_cost_usd": "10.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                    {
                        "provider": "local",
                        "model": "missing-cost",
                        "score": "0.90",
                        "average_latency_ms": "900",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    report = build_exit_report(input_path=path, baseline_ref="openai:gpt-4o", candidate_ref="local:missing-cost")
    assert "Cost is unknown" in render_exit_report_markdown(report)
    assert '"decision"' in render_exit_report_json(report)


def test_markdown_escapes_user_controlled_values(tmp_path: Path) -> None:
    path = tmp_path / "evil.json"
    path.write_text(
        json.dumps(
            {
                "workload": "<script>alert(1)</script>",
                "summaries": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "label": "<b>baseline</b>",
                        "score": "0.90",
                        "average_latency_ms": "1000",
                        "estimated_cost_usd": "10.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:3b",
                        "label": "<img src=x onerror=alert(1)>",
                        "score": "0.85",
                        "average_latency_ms": "900",
                        "estimated_cost_usd": "3.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    report = build_exit_report(input_path=path, baseline_ref="openai:gpt-4o", candidate_ref="ollama:qwen2.5:3b")
    markdown = render_exit_report_markdown(report)
    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "&lt;script&gt;" in markdown


def test_invalid_thresholds_and_risk_profile_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="finite"):
        ExitReportThresholds(min_quality_retention_pct=Decimal("-1"))

    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "summaries": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "score": "0.90",
                        "average_latency_ms": "1000",
                        "estimated_cost_usd": "10.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:3b",
                        "score": "0.85",
                        "average_latency_ms": "900",
                        "estimated_cost_usd": "3.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="risk profile"):
        build_exit_report(input_path=path, baseline_ref="openai:gpt-4o", candidate_ref="ollama:qwen2.5:3b", risk_profile="unknown")

    invalid_decimal = tmp_path / "invalid.jsonl"
    invalid_decimal.write_text('{"provider":"openai","model":"gpt-4o","score":"NaN"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid decimal"):
        load_exit_summaries(invalid_decimal)


def test_cli_exit_report_smoke_and_no_personal_identity(tmp_path: Path) -> None:
    input_path = tmp_path / "results.json"
    output_path = tmp_path / "exit.md"
    input_path.write_text(
        json.dumps(
            {
                "summaries": [
                    {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "score": "0.90",
                        "average_latency_ms": "1000",
                        "estimated_cost_usd": "10.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:3b",
                        "score": "0.82",
                        "average_latency_ms": "800",
                        "estimated_cost_usd": "2.00",
                        "sample_count": 5,
                        "failure_count": 0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "exit-report",
            "--baseline",
            "openai:gpt-4o",
            "--candidate",
            "ollama:qwen2.5:3b",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == 0
    text = output_path.read_text(encoding="utf-8")
    assert "AI Vendor Exit Report" in text
    assert "Candidate acceptable" in text
    assert "@" not in text

    json_output = tmp_path / "exit.json"
    json_result = runner.invoke(
        app,
        [
            "exit-report",
            "--baseline",
            "openai:gpt-4o",
            "--candidate",
            "ollama:qwen2.5:3b",
            "--input",
            str(input_path),
            "--output",
            str(json_output),
            "--format",
            "json",
        ],
    )
    assert json_result.exit_code == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["decision"]["decision"] == "Candidate acceptable"

    bad_result = runner.invoke(
        app,
        [
            "exit-report",
            "--baseline",
            "openai:gpt-4o",
            "--candidate",
            "ollama:qwen2.5:3b",
            "--input",
            str(input_path),
            "--output",
            str(tmp_path / "bad.txt"),
            "--format",
            "html",
        ],
    )
    assert bad_result.exit_code == 2
