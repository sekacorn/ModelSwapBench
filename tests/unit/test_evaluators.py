from __future__ import annotations

from model_swap_bench.config.models import BenchmarkCase, EvaluatorSpec, PolicyExpectation
from model_swap_bench.evaluators import EvalContext, resolve_evaluator
from model_swap_bench.results import EvalStatus, ToolCallRecord


def _run(name: str, ctx: EvalContext, **options: object):  # type: ignore[no-untyped-def]
    return resolve_evaluator(EvaluatorSpec(name=name, options=options)).evaluate(ctx)


def test_json_parse_and_schema_and_field_match() -> None:
    case = BenchmarkCase(id="c", expected={"category": "billing", "escalation_required": True})
    ctx = EvalContext(case=case, output_text='{"category":"billing","escalation_required":true}')
    assert _run("json_parse", ctx).passed
    assert _run("json_schema", ctx).passed
    assert _run("field_match", ctx).passed


def test_json_parse_invalid() -> None:
    ctx = EvalContext(case=BenchmarkCase(id="c"), output_text="not json")
    assert not _run("json_parse", ctx).passed


def test_field_match_mismatch_partial_score() -> None:
    case = BenchmarkCase(id="c", expected={"a": 1, "b": 2})
    ctx = EvalContext(case=case, output_text='{"a":1,"b":99}')
    r = _run("field_match", ctx)
    assert not r.passed
    assert 0.0 < r.score < 1.0


def test_contains_and_forbidden() -> None:
    case = BenchmarkCase(id="c", forbidden_content=["secret"], required_content=["hello"])
    ctx = EvalContext(case=case, output_text="hello world")
    assert _run("contains", ctx).passed
    ctx2 = EvalContext(case=case, output_text="hello secret")
    assert not _run("contains", ctx2).passed


def test_regex() -> None:
    ctx = EvalContext(case=BenchmarkCase(id="c"), output_text="order 12345")
    assert _run("regex", ctx, pattern=r"\d{5}").passed
    assert not _run("regex", ctx, pattern=r"[A-Z]{5}").passed


def test_exact_match() -> None:
    case = BenchmarkCase(id="c", expected_text="yes")
    assert _run("exact_match", EvalContext(case=case, output_text="yes")).passed
    assert not _run("exact_match", EvalContext(case=case, output_text="no")).passed


def test_tool_selection() -> None:
    case = BenchmarkCase(id="c", expected_tool_calls=["escalate"], forbidden_tools=["delete"])
    good = EvalContext(case=case, output_text="", tool_calls=[ToolCallRecord(name="escalate")])
    bad = EvalContext(case=case, output_text="", tool_calls=[ToolCallRecord(name="delete")])
    assert _run("tool_selection", good).passed
    assert not _run("tool_selection", bad).passed


def test_policy_compliance_refusal() -> None:
    case = BenchmarkCase(id="c", policy=PolicyExpectation(require_refusal=True))
    ok = EvalContext(case=case, output_text="I cannot help with that request.")
    bad = EvalContext(case=case, output_text="Sure, here you go.")
    assert _run("policy_compliance", ok).passed
    assert not _run("policy_compliance", bad).passed


def test_citation() -> None:
    case = BenchmarkCase(id="c", expected_citations=["S1"])
    ok = EvalContext(case=case, output_text="answer [S1]")
    assert _run("citation", ok, allowed=["S1"]).passed
    fabricated = EvalContext(case=case, output_text="answer [S9]")
    assert not _run("citation", fabricated, allowed=["S1"]).passed


def test_latency_and_cost() -> None:
    ctx = EvalContext(case=BenchmarkCase(id="c"), output_text="x", latency_ms=100, cost_usd=0.001)
    assert _run("latency", ctx, max_ms=500).passed
    assert not _run("latency", ctx, max_ms=50).passed
    assert _run("cost", ctx, max_usd=0.01).passed
    assert not _run("cost", ctx, max_usd=0.0001).passed


def test_rubric_keyword_and_skip() -> None:
    ctx = EvalContext(case=BenchmarkCase(id="c"), output_text="the answer is helpful and clear")
    passed = _run("rubric", ctx, mode="keyword", keywords=["helpful", "clear"], threshold=0.5)
    assert passed.passed
    skipped = _run("rubric", ctx, mode="judge")
    assert skipped.status is EvalStatus.SKIPPED
