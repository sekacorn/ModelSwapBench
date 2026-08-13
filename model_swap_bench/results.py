"""Runtime result models produced by executing a benchmark.

These are distinct from the *configuration* models in :mod:`model_swap_bench.config`:
config models describe what to run, result models describe what happened.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from model_swap_bench.statistics import ConfidenceInterval, DistributionEvidence


def utcnow() -> datetime:
    """Timezone-aware UTC now (avoids naive-datetime bugs)."""
    return datetime.now(UTC)


class CaseStatus(str, Enum):
    """Outcome of a single case execution."""

    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class EvalStatus(str, Enum):
    """Outcome of a single evaluator."""

    # Status value, not a credential.
    PASS = "pass"  # nosec B105
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class TokenUsage(BaseModel):
    """Token accounting, where the provider reports it."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class ToolCallRecord(BaseModel):
    """A tool/function call reported by a model."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class PolicyEvent(BaseModel):
    """A policy-relevant event recorded during execution."""

    kind: str
    detail: str = ""


class EvaluationResult(BaseModel):
    """The result of one evaluator applied to one case output."""

    evaluator: str
    passed: bool
    score: float = 0.0
    weight: float = 1.0
    confidence: float = 1.0
    status: EvalStatus = EvalStatus.PASS
    explanation: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    expected: Any | None = None
    actual: Any | None = None
    error: str | None = None


class ProviderCall(BaseModel):
    """Metadata about the underlying model call (for transparency / reproducibility)."""

    provider: str
    requested_model: str
    reported_model: str | None = None
    execution_path: str = "direct"
    endpoint: str | None = None


class CaseResult(BaseModel):
    """The result of running one case against one model."""

    run_id: str
    case_id: str
    model_alias: str
    status: CaseStatus
    raw_output: str | None = None
    parsed_output: Any | None = None
    latency_ms: float = 0.0
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    #: Estimated cost of the call. ``None`` means the cost is *unknown* (e.g. a
    #: hosted model with no configured pricing) — distinct from a known ``0.0``
    #: for a genuinely free local/offline call. Unknown cost is never treated as
    #: zero downstream.
    estimated_cost_usd: float | None = None
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    policy_events: list[PolicyEvent] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    retries: int = 0
    escalated: bool = False
    weight: float = 1.0
    provider_call: ProviderCall | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime = Field(default_factory=utcnow)

    @property
    def quality_score(self) -> float:
        """Weighted mean evaluator score over non-skipped evaluators."""
        scored = [e for e in self.evaluations if e.status is not EvalStatus.SKIPPED]
        if not scored:
            return 1.0 if self.status is CaseStatus.SUCCESS else 0.0
        total_weight = sum(e.weight for e in scored) or 1.0
        return sum(e.score * e.weight for e in scored) / total_weight

    @property
    def valid_json(self) -> bool:
        return self.parsed_output is not None


class ModelSummary(BaseModel):
    """Aggregate metrics for one model across all cases in a run."""

    model_alias: str
    provider: str
    deployment: str
    total_cases: int = 0
    successful_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    timeout_cases: int = 0
    success_rate: float = 0.0
    quality_score: float = 0.0
    #: Fraction of JSON-required cases (those with a ``json_parse``/``json_schema``
    #: evaluator) that produced parseable JSON. ``None`` when no case required JSON
    #: (not applicable / not evaluated) — never silently 1.0.
    valid_json_rate: float | None = None
    #: Fraction of policy-evaluated cases that passed. ``None`` when no policy
    #: evidence was collected (not evaluated) — never silently 1.0.
    policy_pass_rate: float | None = None
    tool_accuracy: float | None = None
    avg_latency_ms: float = 0.0
    median_latency_ms: float = 0.0
    p90_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    #: Total estimated cost across executed cases. ``None`` means cost is unknown
    #: (at least one executed case has unknown cost, or none were executed) —
    #: distinct from a known ``0.0`` for a genuinely free local run.
    total_cost_usd: float | None = None
    cost_per_success_usd: float | None = None
    timeout_rate: float = 0.0
    retry_rate: float = 0.0
    escalation_rate: float = 0.0
    error_rate: float = 0.0
    success_rate_confidence_interval: ConfidenceInterval | None = None
    quality_confidence_interval: ConfidenceInterval | None = None
    latency_distribution: DistributionEvidence | None = None
    quality_distribution: DistributionEvidence | None = None
    minimum_recommended_sample_size: int = 20
    evidence_sufficient: bool = True
    evidence_warnings: list[str] = Field(default_factory=list)


class ReplacementDecision(BaseModel):
    """A transparent, evidence-backed replacement recommendation."""

    baseline_model: str
    candidate_model: str
    eligible: bool
    recommendation: str
    confidence: float
    quality_delta: float
    cost_delta_usd: float | None
    cost_reduction_ratio: float | None
    latency_delta_ms: float
    reliability_delta: float
    policy_pass: bool
    deployment_compatible: bool
    failed_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_next_step: str = ""


class CascadeSummary(BaseModel):
    """Economics of a cascade (cheap-first, escalate-on-failure) strategy."""

    first_stage_model: str
    escalation_model: str
    total_cases: int
    first_stage_success: int
    escalated_cases: int
    final_success: int
    escalation_rate: float
    first_stage_success_rate: float
    final_success_rate: float
    total_cost_usd: float | None
    cost_per_success_usd: float | None


class ConstraintResult(BaseModel):
    """The result of checking one suite-level constraint for one model."""

    name: str
    passed: bool
    threshold: float | bool | None
    actual: float | bool | None
    detail: str = ""


class BenchmarkRun(BaseModel):
    """Everything produced by executing a benchmark suite."""

    run_id: str
    suite_name: str
    suite_version: str
    mode: str
    created_at: datetime = Field(default_factory=utcnow)
    baseline_model: str | None = None
    case_results: list[CaseResult] = Field(default_factory=list)
    model_summaries: list[ModelSummary] = Field(default_factory=list)
    constraint_results: dict[str, list[ConstraintResult]] = Field(default_factory=dict)
    replacement_decisions: list[ReplacementDecision] = Field(default_factory=list)
    cascade_summary: CascadeSummary | None = None
    manifest_hash: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def summary_for(self, alias: str) -> ModelSummary | None:
        for summary in self.model_summaries:
            if summary.model_alias == alias:
                return summary
        return None

    @property
    def all_constraints_passed(self) -> bool:
        return all(c.passed for results in self.constraint_results.values() for c in results)
