"""Per-case latency constraint evaluator."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class LatencyConstraintEvaluator(Evaluator):
    """Passes when case latency is within ``options['max_ms']`` (or the case timeout)."""

    name = "latency"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        max_ms = self.options.get("max_ms")
        if max_ms is None and ctx.case.timeout_override is not None:
            max_ms = ctx.case.timeout_override * 1000.0
        if max_ms is None:
            return self._skip("no latency budget configured")
        passed = ctx.latency_ms <= float(max_ms)
        return self._result(
            passed=passed,
            explanation=f"latency {ctx.latency_ms:.0f}ms {'within' if passed else 'exceeds'} budget {float(max_ms):.0f}ms",
            expected=float(max_ms),
            actual=ctx.latency_ms,
        )
