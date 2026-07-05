"""Exact-string-match evaluator."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, normalize_str, register
from model_swap_bench.results import EvaluationResult


@register
class ExactMatchEvaluator(Evaluator):
    """Compares the raw output to ``case.expected_text`` (or ``options['expected']``)."""

    name = "exact_match"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        expected = self.options.get("expected", ctx.case.expected_text)
        if expected is None:
            return self._skip("no expected_text configured for exact_match")
        whitespace = bool(self.options.get("normalize_whitespace", True))
        ignore_case = bool(self.options.get("ignore_case", False))
        actual_n = normalize_str(ctx.output_text, whitespace=whitespace, case=ignore_case)
        expected_n = normalize_str(str(expected), whitespace=whitespace, case=ignore_case)
        passed = actual_n == expected_n
        return self._result(
            passed=passed,
            explanation="exact match" if passed else "output differs from expected text",
            expected=expected,
            actual=ctx.output_text,
        )
