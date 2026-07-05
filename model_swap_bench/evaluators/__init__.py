"""Pluggable evaluators. Importing this package registers all built-in evaluators."""

from __future__ import annotations

# Import for side effect: each module registers its evaluator with the registry.
from model_swap_bench.evaluators import (  # noqa: F401  (registration side effects)
    citation,
    contains,
    cost,
    exact_match,
    field_match,
    json_parse,
    json_schema,
    latency,
    policy,
    regex,
    rubric,
    tool_selection,
)
from model_swap_bench.evaluators.base import (
    EvalContext,
    Evaluator,
    register,
    registered_names,
    resolve_evaluator,
)

__all__ = [
    "EvalContext",
    "Evaluator",
    "register",
    "registered_names",
    "resolve_evaluator",
]
