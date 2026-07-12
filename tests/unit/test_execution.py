from __future__ import annotations

import pytest

from model_swap_bench.config import build_suite
from model_swap_bench.errors import ConfigError
from model_swap_bench.execution import BenchmarkRunner
from model_swap_bench.results import CaseStatus
from tests.conftest import make_suite_dict


async def test_deterministic_run_all_pass(suite) -> None:  # type: ignore[no-untyped-def]
    run = await BenchmarkRunner(suite).run()
    assert len(run.case_results) == 4  # 2 models x 2 cases
    assert run.all_constraints_passed
    assert run.summary_for("baseline").success_rate == 1.0
    assert run.replacement_decisions


async def test_malformed_json_marks_failed() -> None:
    d = make_suite_dict()
    d["models"] = [
        {
            "alias": "m",
            "provider": "deterministic",
            "model": "x",
            "deployment": "test",
            "metadata": {"strategy": "static", "output": "not json"},
        },
    ]
    d["baseline_model"] = "m"
    d.pop("replacement")
    suite = build_suite(d)
    run = await BenchmarkRunner(suite).run(only_models={"m"})
    assert all(r.status is CaseStatus.FAILED for r in run.case_results)


async def test_only_model_filter(suite) -> None:  # type: ignore[no-untyped-def]
    run = await BenchmarkRunner(suite).run(only_models={"candidate"})
    aliases = {r.model_alias for r in run.case_results}
    assert aliases == {"candidate"}


async def test_only_model_filter_rejects_unknown_alias(suite) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfigError, match="unknown model alias"):
        await BenchmarkRunner(suite).run(only_models={"missing"})


async def test_cascade_escalation() -> None:
    d = {
        "name": "casc",
        "models": [
            {
                "alias": "first",
                "provider": "deterministic",
                "model": "s",
                "deployment": "local",
                "metadata": {"strategy": "static", "output": "not json"},
            },
            {"alias": "strong", "provider": "deterministic", "model": "b", "deployment": "test", "metadata": {"strategy": "oracle"}},
        ],
        "cases": [{"id": "c1", "input": {"m": "x"}, "expected": {"a": 1}}],
        "evaluators": ["json_parse", "field_match"],
        "cascade": {"first_stage": "first", "escalation_model": "strong", "conditions": ["invalid_json", "evaluator_failure"]},
        "constraints": {"minimum_success_rate": 0.5},
    }
    suite = build_suite(d)
    run = await BenchmarkRunner(suite).run()
    assert run.cascade_summary is not None
    assert run.cascade_summary.escalated_cases == 1
    assert run.cascade_summary.final_success == 1


async def test_retry_on_transient_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A fixture that always errors should consume the configured retries then fail as ERROR.
    fx = tmp_path / "fx.yaml"
    fx.write_text("cases:\n  c1: {status: error}\n", encoding="utf-8")
    d = {
        "name": "retry",
        "models": [
            {
                "alias": "m",
                "provider": "deterministic",
                "model": "x",
                "deployment": "test",
                "fixture": str(fx),
                "retries": 2,
                "metadata": {"strategy": "fixture"},
            }
        ],
        "cases": [{"id": "c1", "input": {"m": "x"}, "expected": {"a": 1}}],
        "evaluators": ["json_parse"],
        "execution": {"retries": 2},
    }
    suite = build_suite(d)
    run = await BenchmarkRunner(suite).run(only_models={"m"})
    result = run.case_results[0]
    assert result.status is CaseStatus.ERROR
    assert result.retries == 2
