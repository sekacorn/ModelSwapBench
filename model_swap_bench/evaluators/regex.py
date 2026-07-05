"""Regular-expression evaluator with a bounded input size (basic ReDoS mitigation)."""

from __future__ import annotations

import re

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult

#: Cap the text length fed to the regex engine to bound worst-case backtracking.
MAX_REGEX_INPUT = 100_000


@register
class RegexEvaluator(Evaluator):
    """Requires ``options['pattern']`` to match and ``options['forbidden_pattern']`` not to."""

    name = "regex"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        pattern = self.options.get("pattern")
        forbidden = self.options.get("forbidden_pattern")
        if not pattern and not forbidden:
            return self._skip("no pattern configured for regex evaluator")
        text = ctx.output_text[:MAX_REGEX_INPUT]
        flags = re.IGNORECASE if self.options.get("ignore_case") else 0
        required_ok = True
        forbidden_ok = True
        if pattern:
            required_ok = re.search(str(pattern), text, flags) is not None
        if forbidden:
            forbidden_ok = re.search(str(forbidden), text, flags) is None
        passed = required_ok and forbidden_ok
        return self._result(
            passed=passed,
            explanation="regex constraints satisfied" if passed else "regex constraints violated",
            evidence={"pattern_matched": required_ok, "forbidden_absent": forbidden_ok},
            expected=pattern,
        )
