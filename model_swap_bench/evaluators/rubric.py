"""Optional model-assisted (or keyword-heuristic) rubric evaluator.

By design this is never the only evaluator, must identify its judge, and is
disabled in fully deterministic CI. For v0.1 it supports a deterministic
``keyword`` mode (offline, clearly labeled as a heuristic, not a judgment of
truth). A real judge-model mode is on the roadmap; without a configured judge it
skips rather than fabricating a score.
"""

from __future__ import annotations

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult


@register
class RubricEvaluator(Evaluator):
    """Heuristic/keyword rubric (offline) or skip when no judge is configured."""

    name = "rubric"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        mode = str(self.options.get("mode", "keyword" if self.options.get("keywords") else "judge"))
        if mode == "judge":
            return self._skip("rubric judge-model mode is not enabled in v0.1; configure mode: keyword for offline use")
        keywords = [str(k).lower() for k in self.options.get("keywords", [])]
        if not keywords:
            return self._skip("keyword rubric requires options.keywords")
        lower = ctx.output_text.lower()
        hits = [k for k in keywords if k in lower]
        score = len(hits) / len(keywords)
        threshold = float(self.options.get("threshold", 0.5))
        passed = score >= threshold
        return self._result(
            passed=passed,
            score=score,
            confidence=0.5,  # heuristic — lower confidence than deterministic checks
            explanation=f"keyword rubric matched {len(hits)}/{len(keywords)} (heuristic, not ground truth)",
            evidence={"matched": hits, "judge": "keyword-heuristic", "threshold": threshold},
        )
