"""JSON Schema evaluator.

Uses ``case.expected_schema`` when provided; otherwise derives a minimal schema
from the keys/types of ``case.expected`` so a bare ``json_schema`` evaluator is
still meaningful for structured-output cases.
"""

from __future__ import annotations

from typing import Any

import jsonschema

from model_swap_bench.evaluators.base import EvalContext, Evaluator, register
from model_swap_bench.results import EvaluationResult

_TYPE_MAP: dict[type, str] = {bool: "boolean", int: "integer", float: "number", str: "string", list: "array", dict: "object"}


def derive_schema(expected: dict[str, Any]) -> dict[str, Any]:
    """Build an object schema requiring the keys of ``expected`` with matching types."""
    props: dict[str, Any] = {}
    for key, value in expected.items():
        json_type = _TYPE_MAP.get(type(value))
        props[key] = {"type": json_type} if json_type else {}
    return {"type": "object", "properties": props, "required": list(expected.keys())}


@register
class JSONSchemaEvaluator(Evaluator):
    """Validates parsed output against a JSON Schema."""

    name = "json_schema"

    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        schema = self.options.get("schema") or ctx.case.expected_schema
        if schema is None and ctx.case.expected is not None:
            schema = derive_schema(ctx.case.expected)
        if schema is None:
            return self._skip("no expected_schema and no expected object to derive one from")
        parsed = ctx.ensure_parsed()
        if parsed is None:
            return self._result(passed=False, explanation="output is not valid JSON", actual=ctx.output_text[:200])
        try:
            jsonschema.validate(instance=parsed, schema=schema)
        except jsonschema.ValidationError as exc:
            return self._result(
                passed=False,
                explanation=f"schema validation failed: {exc.message}",
                evidence={"path": list(exc.absolute_path)},
                actual=parsed,
            )
        return self._result(passed=True, explanation="output conforms to schema", actual=parsed)
