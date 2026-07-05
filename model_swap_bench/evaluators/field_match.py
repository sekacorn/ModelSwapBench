"""Field-level comparison of parsed JSON output against expected values."""

from __future__ import annotations

from typing import Any

from model_swap_bench.evaluators.base import EvalContext, Evaluator, normalize_str, register
from model_swap_bench.results import EvaluationResult


def _matches(expected: Any, actual: Any, *, tolerance: float, normalize: bool) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(expected == actual)
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= tolerance
    if isinstance(expected, list):
        return isinstance(actual, list) and all(item in actual for item in expected)
    if isinstance(expected, str) and isinstance(actual, str) and normalize:
        return normalize_str(expected, whitespace=True, case=True) == normalize_str(actual, whitespace=True, case=True)
    return bool(expected == actual)


@register
class FieldMatchEvaluator(Evaluator):
    """Compares selected JSON fields with exact / tolerance / membership / normalized rules."""

    name = "field_match"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        expected = self.options.get("expected") or ctx.case.expected
        if not expected:
            return self._skip("no expected object configured for field_match")
        parsed = ctx.ensure_parsed()
        if not isinstance(parsed, dict):
            return self._result(passed=False, explanation="output is not a JSON object", actual=ctx.output_text[:200])
        fields = list(self.options.get("fields", [])) or list(expected.keys())
        tolerance = float(self.options.get("tolerance", 0.0))
        normalize = bool(self.options.get("normalize", True))
        mismatches: dict[str, Any] = {}
        for key in fields:
            exp = expected.get(key)
            act = parsed.get(key)
            if not _matches(exp, act, tolerance=tolerance, normalize=normalize):
                mismatches[key] = {"expected": exp, "actual": act}
        matched = len(fields) - len(mismatches)
        score = matched / len(fields) if fields else 1.0
        passed = not mismatches
        return self._result(
            passed=passed,
            score=score,
            explanation="all fields match" if passed else f"{len(mismatches)} field(s) mismatched",
            evidence={"mismatches": mismatches},
            expected=expected,
            actual=parsed,
        )
