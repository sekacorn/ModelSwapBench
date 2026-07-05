"""Semantic (cross-field) validation of a benchmark suite.

Pydantic validates individual field types; this module enforces relationships
between fields (unique aliases, references that resolve, known evaluator names).
"""

from __future__ import annotations

from collections import Counter

from model_swap_bench.config.models import BenchmarkSuite
from model_swap_bench.errors import ValidationError

#: Canonical evaluator names plus documented aliases accepted in YAML.
KNOWN_EVALUATORS: frozenset[str] = frozenset(
    {
        "exact_match",
        "contains",
        "forbidden_content",  # alias -> contains (forbidden substrings)
        "regex",
        "json_parse",
        "json_schema",
        "field_match",
        "tool_selection",
        "policy_compliance",
        "citation",
        "latency",
        "cost",
        "rubric",
    }
)


def validate_suite(suite: BenchmarkSuite) -> None:
    """Raise :class:`ValidationError` if the suite is internally inconsistent."""
    problems: list[str] = []

    if not suite.models:
        problems.append("suite defines no models")
    if not suite.cases:
        problems.append("suite defines no cases")

    aliases = [m.alias for m in suite.models]
    for alias, count in Counter(aliases).items():
        if count > 1:
            problems.append(f"duplicate model alias: {alias!r} ({count}x)")

    case_ids = [c.id for c in suite.cases]
    for case_id, count in Counter(case_ids).items():
        if count > 1:
            problems.append(f"duplicate case id: {case_id!r} ({count}x)")

    alias_set = set(aliases)
    if suite.baseline_model and suite.baseline_model not in alias_set:
        problems.append(f"baseline_model {suite.baseline_model!r} is not a defined model alias")

    if suite.replacement:
        if suite.replacement.baseline not in alias_set:
            problems.append(f"replacement.baseline {suite.replacement.baseline!r} is not a defined model alias")
        for candidate in suite.replacement.candidates:
            if candidate not in alias_set:
                problems.append(f"replacement candidate {candidate!r} is not a defined model alias")

    if suite.cascade:
        if suite.cascade.first_stage not in alias_set:
            problems.append(f"cascade.first_stage {suite.cascade.first_stage!r} is not a defined model alias")
        if suite.cascade.escalation_model not in alias_set:
            problems.append(f"cascade.escalation_model {suite.cascade.escalation_model!r} is not a defined model alias")

    for spec in suite.evaluators:
        if spec.name not in KNOWN_EVALUATORS:
            problems.append(f"unknown evaluator: {spec.name!r}")
    for case in suite.cases:
        for spec in case.evaluators:
            if spec.name not in KNOWN_EVALUATORS:
                problems.append(f"case {case.id!r}: unknown evaluator {spec.name!r}")

    if problems:
        raise ValidationError("Benchmark suite is invalid:\n" + "\n".join(f"  - {p}" for p in problems))
