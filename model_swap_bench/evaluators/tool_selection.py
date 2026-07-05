"""Tool-selection correctness evaluator."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class ToolSelectionEvaluator(Evaluator):
    """Verifies expected tools were called, optionally in order, and forbidden tools were not."""

    name = "tool_selection"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        expected = list(self.options.get("expected", [])) or list(ctx.case.expected_tool_calls)
        forbidden = list(self.options.get("forbidden", [])) or list(ctx.case.forbidden_tools)
        if not expected and not forbidden:
            return self._skip("no expected/forbidden tools configured")
        called = [tc.name for tc in ctx.tool_calls]
        ordered = bool(self.options.get("ordered", False))
        missing = [t for t in expected if t not in called]
        present_forbidden = [t for t in forbidden if t in called]
        order_ok = True
        if ordered and expected:
            order_ok = [t for t in called if t in expected] == expected
        checks = len(expected) + len(forbidden)
        satisfied = checks - len(missing) - len(present_forbidden)
        score = (satisfied / checks) if checks else 1.0
        passed = not missing and not present_forbidden and order_ok
        return self._result(
            passed=passed,
            score=score,
            explanation="tool selection correct" if passed else "tool selection incorrect",
            evidence={"called": called, "missing": missing, "forbidden_called": present_forbidden, "order_ok": order_ok},
            expected=expected,
            actual=called,
        )
