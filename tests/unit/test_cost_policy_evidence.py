"""P0 Beta hardening: unknown cost and unevaluated policy/JSON must never
collapse into a favorable numeric default (zero cost / 100% pass).

These regression tests lock in the rule shared with the gate/route-plan/outcome
paths: UNKNOWN != ZERO, UNKNOWN != PASS, INSUFFICIENT != SUCCESS.
"""

from __future__ import annotations

import json

from model_swap_bench.config.models import (
    DeploymentType,
    ModelCandidate,
    ProviderKind,
    ReplacementConfig,
    ScoringConfig,
)
from model_swap_bench.reports.csv_report import render_csv
from model_swap_bench.reports.exit_report import (
    BenchmarkSummary,
    ExitDecision,
    ExitReportThresholds,
    _summaries_from_run,
    decide_exit,
)
from model_swap_bench.reports.markdown import _summary_row
from model_swap_bench.results import BenchmarkRun, CaseResult, CaseStatus, EvalStatus, EvaluationResult
from model_swap_bench.scoring import economics
from model_swap_bench.scoring.aggregation import build_model_summary
from model_swap_bench.scoring.replacement import decide_replacement

# --------------------------------------------------------------------------- helpers


def _candidate(alias: str, provider: ProviderKind, deployment: DeploymentType, **prices: float) -> ModelCandidate:
    return ModelCandidate(alias=alias, provider=provider, model="m", deployment=deployment, **prices)


def _results(alias: str, n: int, *, cost, quality=0.9, with_policy=False, with_json=False, policy_pass=True) -> list[CaseResult]:
    out: list[CaseResult] = []
    for i in range(n):
        evals = [EvaluationResult(evaluator="rubric", passed=True, score=quality, status=EvalStatus.PASS)]
        if with_policy:
            evals.append(
                EvaluationResult(
                    evaluator="policy_compliance",
                    passed=policy_pass,
                    score=1.0 if policy_pass else 0.0,
                    status=EvalStatus.PASS if policy_pass else EvalStatus.FAIL,
                )
            )
        if with_json:
            evals.append(EvaluationResult(evaluator="json_parse", passed=True, score=1.0, status=EvalStatus.PASS))
        out.append(
            CaseResult(
                run_id="r",
                case_id=f"{alias}-{i}",
                model_alias=alias,
                status=CaseStatus.SUCCESS,
                latency_ms=100.0,
                estimated_cost_usd=cost,
                evaluations=evals,
                parsed_output={"ok": True} if with_json else None,
            )
        )
    return out


_SCORING = ScoringConfig()
_LOCAL = _candidate("base", ProviderKind.OLLAMA, DeploymentType.LOCAL)
_HOSTED_NO_PRICE = _candidate("cand", ProviderKind.OPENAI, DeploymentType.HOSTED)


# --------------------------------------------------------------------------- economics


def test_estimate_call_cost_local_without_pricing_is_known_zero() -> None:
    # (4) TRUE ZERO COST: local/offline with no declared pricing is a known 0, not unknown.
    cost = economics.estimate_call_cost(_LOCAL, _SCORING, input_tokens=1000, output_tokens=1000, latency_ms=50.0)
    assert cost == 0.0


def test_estimate_call_cost_hosted_without_pricing_is_unknown() -> None:
    # (1) UNKNOWN CANDIDATE COST: hosted provider without pricing -> None, never 0.
    cost = economics.estimate_call_cost(_HOSTED_NO_PRICE, _SCORING, input_tokens=1000, output_tokens=1000, latency_ms=50.0)
    assert cost is None


def test_estimate_call_cost_priced_hosted_is_computed() -> None:
    # (5) FULLY PRICED: unchanged arithmetic.
    priced = _candidate(
        "p",
        ProviderKind.OPENAI,
        DeploymentType.HOSTED,
        estimated_input_cost_per_million=2.0,
        estimated_output_cost_per_million=4.0,
    )
    cost = economics.estimate_call_cost(priced, _SCORING, input_tokens=1_000_000, output_tokens=1_000_000, latency_ms=1.0)
    assert cost == 6.0


def test_explicit_zero_price_hosted_is_known_zero() -> None:
    free = _candidate(
        "f",
        ProviderKind.OPENAI,
        DeploymentType.HOSTED,
        estimated_input_cost_per_million=0.0,
        estimated_output_cost_per_million=0.0,
    )
    assert economics.estimate_call_cost(free, _SCORING, input_tokens=99, output_tokens=99, latency_ms=1.0) == 0.0


def test_cost_per_success_unknown_total_is_none() -> None:
    assert economics.cost_per_success(None, 10) is None
    assert economics.cost_per_success(1.0, 0) is None
    assert economics.cost_per_success(2.0, 4) == 0.5


# --------------------------------------------------------------------------- aggregation


def test_summary_unknown_cost_stays_unknown() -> None:
    summary = build_model_summary(_HOSTED_NO_PRICE, _results("cand", 20, cost=None))
    assert summary.total_cost_usd is None
    assert summary.cost_per_success_usd is None


def test_summary_true_zero_cost_stays_zero() -> None:
    summary = build_model_summary(_LOCAL, _results("base", 20, cost=0.0))
    assert summary.total_cost_usd == 0.0


def test_summary_no_policy_cases_is_none_not_one() -> None:
    # (6) NO POLICY CASES: policy_pass_rate is None, not 1.0.
    summary = build_model_summary(_HOSTED_NO_PRICE, _results("cand", 20, cost=0.1, with_policy=False))
    assert summary.policy_pass_rate is None


def test_summary_policy_cases_present_measures_rate() -> None:
    # (7) POLICY CASES PRESENT: measured rate preserved.
    good = _results("cand", 18, cost=0.1, with_policy=True, policy_pass=True)
    bad = _results("cand", 2, cost=0.1, with_policy=True, policy_pass=False)
    summary = build_model_summary(_HOSTED_NO_PRICE, good + bad)
    assert summary.policy_pass_rate == 0.9


def test_summary_no_json_cases_is_none_not_one() -> None:
    # (8) VALID JSON NOT EVALUATED: None (not applicable), not 1.0.
    summary = build_model_summary(_LOCAL, _results("base", 20, cost=0.0, with_json=False))
    assert summary.valid_json_rate is None


def test_summary_json_cases_present_measures_rate() -> None:
    summary = build_model_summary(_LOCAL, _results("base", 20, cost=0.0, with_json=True))
    assert summary.valid_json_rate == 1.0  # measured over the 20 JSON-required cases


# --------------------------------------------------------------------------- decision engine


def _decide(baseline_cost, candidate_cost, *, candidate=_HOSTED_NO_PRICE, with_policy=False):
    bsum = build_model_summary(_LOCAL, _results("base", 20, cost=baseline_cost, with_policy=with_policy))
    csum = build_model_summary(candidate, _results("cand", 20, cost=candidate_cost, with_policy=with_policy))
    cfg = ReplacementConfig(baseline="base", candidates=["cand"], minimum_cost_reduction=0.2)
    return decide_replacement(bsum, csum, candidate, cfg, candidate_constraints=[], privacy_allows_hosted=True)


def test_unknown_candidate_cost_no_savings_claim() -> None:
    # (1) unknown candidate cost -> no cost reduction, explicit uncertainty, conditions attached.
    d = _decide(baseline_cost=0.1, candidate_cost=None)
    assert d.cost_reduction_ratio is None
    assert d.recommendation == "recommended with conditions"
    assert not any("100% cost reduction" in e or "cost reduction vs baseline" in e for e in d.evidence)
    assert any("cost is unknown" in r for r in d.risks)


def test_unknown_baseline_cost_no_bogus_reduction() -> None:
    # (2) UNKNOWN BASELINE COST.
    d = _decide(baseline_cost=None, candidate_cost=0.1)
    assert d.cost_reduction_ratio is None
    assert any("cost is unknown" in r for r in d.risks)


def test_both_costs_unknown_remains_unknown() -> None:
    # (3) BOTH UNKNOWN.
    d = _decide(baseline_cost=None, candidate_cost=None)
    assert d.cost_reduction_ratio is None


def test_fully_priced_comparison_unchanged() -> None:
    # (5) fully priced: real cost reduction still computed and can be recommended.
    priced = _candidate(
        "cand",
        ProviderKind.OPENAI,
        DeploymentType.HOSTED,
        estimated_input_cost_per_million=1.0,
        estimated_output_cost_per_million=1.0,
    )
    d = _decide(baseline_cost=1.0, candidate_cost=0.4, candidate=priced, with_policy=True)
    assert d.cost_reduction_ratio is not None and d.cost_reduction_ratio > 0
    assert d.recommendation == "recommended replacement"


def test_no_policy_evidence_not_a_pass() -> None:
    # (6) decision must not claim policy pass with zero policy evidence.
    d = _decide(baseline_cost=1.0, candidate_cost=0.1, with_policy=False)  # priced so cost is fine
    priced = _candidate(
        "cand",
        ProviderKind.OPENAI,
        DeploymentType.HOSTED,
        estimated_input_cost_per_million=1.0,
        estimated_output_cost_per_million=0.0,
    )
    d = _decide(baseline_cost=1.0, candidate_cost=0.1, candidate=priced, with_policy=False)
    assert d.policy_pass is False
    assert any("policy" in r.lower() for r in d.risks)
    assert d.recommendation == "recommended with conditions"


# --------------------------------------------------------------------------- run -> exit-report bridge


def test_run_exit_report_bridge_hosted_missing_pricing_is_insufficient() -> None:
    # (9) CRITICAL: the flagship vendor-exit report can no longer emit "100% cost reduction"
    # or an unconditional acceptable verdict from a hosted candidate with missing pricing.
    raw = {
        "model_summaries": [
            {
                "provider": "ollama",
                "model_alias": "base",
                "quality_score": 0.9,
                "avg_latency_ms": 100,
                "total_cost_usd": 2.0,
                "total_cases": 20,
                "failed_cases": 0,
                "error_cases": 0,
                "timeout_cases": 0,
            },
            {
                "provider": "openai",
                "model_alias": "cand",
                "quality_score": 0.89,
                "avg_latency_ms": 80,
                "total_cost_usd": None,
                "total_cases": 20,
                "failed_cases": 0,
                "error_cases": 0,
                "timeout_cases": 0,
            },
        ]
    }
    summaries = [BenchmarkSummary.model_validate(s) for s in _summaries_from_run(raw)]
    base, cand = summaries[0], summaries[1]
    assert cand.estimated_cost_usd is None
    decision = decide_exit(base, cand, ExitReportThresholds(), risk_profile="low")
    assert decision.decision is ExitDecision.INSUFFICIENT
    assert decision.cost_reduction_pct is None


# --------------------------------------------------------------------------- serialization


def test_serialization_unknown_values_are_null_not_zero() -> None:
    # (10) JSON: null.  (11) ROUND TRIP: Optionals survive.
    summary = build_model_summary(_HOSTED_NO_PRICE, _results("cand", 20, cost=None, with_policy=False))
    payload = json.loads(summary.model_dump_json())
    assert payload["total_cost_usd"] is None
    assert payload["policy_pass_rate"] is None
    assert payload["valid_json_rate"] is None
    from model_swap_bench.results import ModelSummary

    restored = ModelSummary.model_validate(payload)
    assert restored.total_cost_usd is None and restored.policy_pass_rate is None and restored.valid_json_rate is None


def test_csv_unknown_cost_not_serialized_as_zero() -> None:
    # (10) CSV: unknown must be blank, never numeric 0.
    run = BenchmarkRun(run_id="r", suite_name="s", suite_version="1", mode="baseline_vs_candidate")
    run.model_summaries.append(build_model_summary(_HOSTED_NO_PRICE, _results("cand", 20, cost=None)))
    csv_text = render_csv(run)
    header, row = csv_text.splitlines()[0], csv_text.splitlines()[1]
    cols = header.split(",")
    values = row.split(",")
    cell = dict(zip(cols, values, strict=True))
    assert cell["total_cost_usd"] == ""  # blank, not "0" or "0.0"
    assert cell["policy_pass_rate"] == ""


def test_markdown_unknown_values_render_na() -> None:
    # (10) Markdown: n/a.
    summary = build_model_summary(_HOSTED_NO_PRICE, _results("cand", 20, cost=None))
    row = _summary_row(summary)
    # policy, valid_json, total cost, cost/success columns are all unknown -> n/a
    assert "n/a" in row
