"""Substring inclusion / exclusion evaluator (also backs the ``forbidden_content`` alias)."""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class ContainsEvaluator(Evaluator):
    """Checks required substrings are present and forbidden substrings are absent."""

    name = "contains"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        forbidden_only = bool(self.options.get("_forbidden_only", False))
        required = list(self.options.get("required", [])) + list(ctx.case.required_content)
        forbidden = list(self.options.get("forbidden", [])) + list(ctx.case.forbidden_content)
        if forbidden_only:
            required = []
        haystack = ctx.output_text
        missing = [s for s in required if s not in haystack]
        present_forbidden = [s for s in forbidden if s in haystack]
        checks = len(required) + len(forbidden)
        if checks == 0:
            return self._skip("no required/forbidden substrings configured")
        satisfied = checks - len(missing) - len(present_forbidden)
        score = satisfied / checks
        passed = not missing and not present_forbidden
        explanation = "all substring constraints satisfied" if passed else "substring constraints violated"
        return self._result(
            passed=passed,
            score=score,
            explanation=explanation,
            evidence={"missing_required": missing, "present_forbidden": present_forbidden},
        )
