# Adding an evaluator

Evaluators are pluggable and registered by name.

```python
from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult

@register
class MyEvaluator(Evaluator):
    name = "my_evaluator"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        # ctx.output_text, ctx.ensure_parsed(), ctx.tool_calls, ctx.latency_ms, ctx.cost_usd
        passed = "hello" in ctx.output_text
        return self._result(
            passed=passed,
            explanation="found greeting" if passed else "no greeting",
            evidence={"len": len(ctx.output_text)},
        )
```

Then:

1. Import your module in `evaluators/__init__.py` so registration runs.
2. Add the name to `config/validation.py::KNOWN_EVALUATORS`.
3. Return an explanation and evidence — never a bare pass/fail.
4. Use `self._skip(...)` when the case doesn't configure your evaluator.
5. Add offline unit tests.

## Rules

- Deterministic by default. A model-assisted evaluator must identify its judge,
  never be the sole evaluator, and be disabled in deterministic CI.
- No arbitrary user code execution (not supported in v0.1).
