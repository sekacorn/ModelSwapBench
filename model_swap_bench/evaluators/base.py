"""Pluggable evaluator interface.

Evaluators are deterministic by default. Each takes an :class:`EvalContext`
(the case plus the model's output and metadata) and returns an
:class:`~model_swap_bench.results.EvaluationResult` with an explanation and
evidence — never just a pass/fail bit.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import Any, ClassVar

from model_swap_bench.config.models import BenchmarkCase, EvaluatorSpec
from model_swap_bench.results import EvalStatus, EvaluationResult, PolicyEvent, ToolCallRecord


@dataclass
class EvalContext:
    """Mutable context shared across evaluators for one case output."""

    case: BenchmarkCase
    output_text: str
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    policy_events: list[PolicyEvent] = field(default_factory=list)
    parsed: Any | None = None
    _parse_attempted: bool = False

    def ensure_parsed(self) -> Any | None:
        """Lazily parse the output as JSON, caching the result (or the failure)."""
        if not self._parse_attempted:
            self._parse_attempted = True
            try:
                self.parsed = json.loads(self.output_text)
            except (json.JSONDecodeError, ValueError):
                self.parsed = None
        return self.parsed


class Evaluator(abc.ABC):
    """Base class for all evaluators."""

    #: Canonical registry name.
    name: ClassVar[str]

    def __init__(self, spec: EvaluatorSpec) -> None:
        self.spec = spec
        self.options: dict[str, Any] = dict(spec.options)
        self.weight = spec.weight

    @abc.abstractmethod
    def evaluate(self, ctx: EvalContext) -> EvaluationResult:
        """Evaluate one case output."""

    # --- helpers -----------------------------------------------------------
    def _result(
        self,
        *,
        passed: bool,
        score: float | None = None,
        explanation: str,
        evidence: dict[str, Any] | None = None,
        expected: Any | None = None,
        actual: Any | None = None,
        status: EvalStatus | None = None,
        confidence: float = 1.0,
    ) -> EvaluationResult:
        if status is None:
            status = EvalStatus.PASS if passed else EvalStatus.FAIL
        if score is None:
            score = 1.0 if passed else 0.0
        return EvaluationResult(
            evaluator=self.name,
            passed=passed,
            score=score,
            weight=self.weight,
            confidence=confidence,
            status=status,
            explanation=explanation,
            evidence=evidence or {},
            expected=expected,
            actual=actual,
        )

    def _skip(self, explanation: str) -> EvaluationResult:
        return EvaluationResult(
            evaluator=self.name,
            passed=True,
            score=1.0,
            weight=self.weight,
            status=EvalStatus.SKIPPED,
            explanation=explanation,
        )


def normalize_str(value: str, *, whitespace: bool = False, case: bool = False) -> str:
    if whitespace:
        value = " ".join(value.split())
    if case:
        value = value.lower()
    return value


_REGISTRY: dict[str, type[Evaluator]] = {}


def register(cls: type[Evaluator]) -> type[Evaluator]:
    """Class decorator to register an evaluator by its ``name``."""
    _REGISTRY[cls.name] = cls
    return cls


def resolve_evaluator(spec: EvaluatorSpec) -> Evaluator:
    """Build an evaluator instance from a spec, handling documented aliases."""
    from model_swap_bench.errors import ConfigError

    name = spec.name
    if name == "forbidden_content":
        # Alias: contains-evaluator wired to the case's forbidden_content list.
        spec = EvaluatorSpec(name="contains", weight=spec.weight, options={**spec.options, "_forbidden_only": True})
        name = "contains"
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ConfigError(f"unknown evaluator: {spec.name!r}")
    return cls(spec)


def registered_names() -> list[str]:
    return sorted(_REGISTRY)
