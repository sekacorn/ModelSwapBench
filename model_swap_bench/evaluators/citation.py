"""Citation-grounding evaluator for local RAG workflows."""

from __future__ import annotations

import re

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult

_DEFAULT_PATTERN = r"\[([A-Za-z0-9_.:-]+)\]"


@register
class CitationEvaluator(Evaluator):
    """Checks required source ids are cited and no unsupported source id appears.

    Citations are extracted from the output (default form ``[S1]``). The universe
    of allowed ids is ``options['allowed']`` or, if absent, the expected citations.
    """

    name = "citation"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        expected = list(self.options.get("expected", [])) or list(ctx.case.expected_citations)
        if not expected and "allowed" not in self.options:
            return self._skip("no expected citations configured")
        pattern = str(self.options.get("pattern", _DEFAULT_PATTERN))
        found = set(re.findall(pattern, ctx.output_text))
        allowed = set(self.options.get("allowed", expected))
        missing = [c for c in expected if c not in found]
        unsupported = [c for c in found if c not in allowed]
        passed = not missing and not unsupported
        checks = max(len(expected), 1)
        score = (checks - len(missing)) / checks if passed or not unsupported else 0.0
        return self._result(
            passed=passed,
            score=1.0 if passed else score if not unsupported else 0.0,
            explanation="citations grounded" if passed else "citation problems detected",
            evidence={"found": sorted(found), "missing": missing, "unsupported": unsupported},
            expected=expected,
        )
