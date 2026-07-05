"""JSON validity evaluator. Populates ``ctx.parsed`` for downstream evaluators."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class JSONParseEvaluator(Evaluator):
    """Passes when the output is valid JSON."""

    name = "json_parse"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        parsed = ctx.ensure_parsed()
        passed = parsed is not None
        return self._result(
            passed=passed,
            explanation="output is valid JSON" if passed else "output is not valid JSON",
            actual=ctx.output_text[:200],
        )
