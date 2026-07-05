"""Per-case cost constraint evaluator."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class CostConstraintEvaluator(Evaluator):
    """Passes when the case's estimated cost is within ``options['max_usd']``."""

    name = "cost"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        max_usd = self.options.get("max_usd")
        if max_usd is None:
            return self._skip("no cost budget configured")
        passed = ctx.cost_usd <= float(max_usd)
        return self._result(
            passed=passed,
            explanation=f"cost ${ctx.cost_usd:.6f} {'within' if passed else 'exceeds'} budget ${float(max_usd):.6f}",
            expected=float(max_usd),
            actual=ctx.cost_usd,
        )
