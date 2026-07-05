"""Typed Pydantic models for the ModelSwapBench benchmark format.

These models define the on-disk YAML/JSON schema. They are intentionally strict
(``extra="forbid"``) so typos in benchmark files surface as validation errors
rather than being silently ignored.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderKind(str, Enum):
    """Supported provider backends."""

    DETERMINISTIC = "deterministic"
    OLLAMA = "ollama"
    FORGE = "forge"
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"


#: Providers that may transmit benchmark data off the local machine.
HOSTED_PROVIDERS: frozenset[ProviderKind] = frozenset(
    {ProviderKind.OPENAI, ProviderKind.ANTHROPIC, ProviderKind.BEDROCK}
)


class DeploymentType(str, Enum):
    """Where a model physically runs — used for privacy/portability classification."""

    LOCAL = "local"
    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"
    TEST = "test"


class ExecutionMode(str, Enum):
    """How a suite is executed across its models."""

    SINGLE = "single"
    COMPARISON = "comparison"
    BASELINE_VS_CANDIDATE = "baseline_vs_candidate"
    CASCADE = "cascade"


class CostMode(str, Enum):
    """How per-call cost is estimated."""

    ZERO_MARGINAL = "zero_marginal"
    ESTIMATED_COMPUTE = "estimated_compute"


class CascadeCondition(str, Enum):
    """Conditions that trigger escalation to the stronger stage in cascade mode."""

    EVALUATOR_FAILURE = "evaluator_failure"
    INVALID_JSON = "invalid_json"
    LOW_SCORE = "low_score"
    POLICY_FAILURE = "policy_failure"
    LOW_CONFIDENCE = "low_confidence"
    TIMEOUT = "timeout"
    CASE_TAG = "case_tag"


class _Strict(BaseModel):
    """Base model that rejects unknown keys to catch benchmark-file typos."""

    model_config = ConfigDict(extra="forbid")


class EvaluatorSpec(_Strict):
    """A reference to an evaluator plus its options.

    In YAML an evaluator may be written either as a bare string (``json_schema``)
    or as a mapping (``{name: field_match, options: {...}}``). Both normalize here.
    """

    name: str
    weight: float = 1.0
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_bare_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value}
        return value


class PolicyExpectation(_Strict):
    """Declarative policy expectations checked by :class:`PolicyComplianceEvaluator`."""

    forbidden_actions: list[str] = Field(default_factory=list)
    require_refusal: bool = False
    require_approval: bool = False
    required_events: list[str] = Field(default_factory=list)


class ComputeCostProfile(_Strict):
    """Operator-supplied estimates for local-compute cost. All values are estimates."""

    electricity_price_per_kwh: float = 0.0
    watts: float = 0.0
    hardware_amortization_per_hour: float = 0.0
    cloud_gpu_hourly_rate: float = 0.0
    fixed_overhead_per_run_usd: float = 0.0


class ModelCandidate(_Strict):
    """A single model configuration under test."""

    alias: str
    provider: ProviderKind
    model: str = Field(description="Provider-specific model id, e.g. 'qwen2.5:3b'.")
    deployment: DeploymentType = DeploymentType.LOCAL
    base_url: str | None = None
    api_key_env: str | None = Field(
        default=None,
        description="Name of the environment variable holding the API key (never the key itself).",
    )
    estimated_input_cost_per_million: float = 0.0
    estimated_output_cost_per_million: float = 0.0
    context_limit: int | None = None
    timeout_seconds: float | None = None
    retries: int | None = None
    temperature: float = 0.0
    seed: int | None = None
    fixture: str | None = Field(default=None, description="Deterministic-provider fixture id.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_hosted(self) -> bool:
        return self.provider in HOSTED_PROVIDERS or self.deployment is DeploymentType.HOSTED


class BenchmarkCase(_Strict):
    """One workflow test executed against every model."""

    id: str
    description: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    prompt: str | None = Field(default=None, description="Explicit prompt override; else built from input.")
    expected: dict[str, Any] | None = None
    expected_text: str | None = None
    expected_schema: dict[str, Any] | None = None
    required_fields: list[str] = Field(default_factory=list)
    forbidden_content: list[str] = Field(default_factory=list)
    required_content: list[str] = Field(default_factory=list)
    expected_tool_calls: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expected_citations: list[str] = Field(default_factory=list)
    policy: PolicyExpectation | None = None
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    timeout_override: float | None = None
    evaluators: list[EvaluatorSpec] = Field(default_factory=list)
    sensitive: bool = False


class Constraints(_Strict):
    """Suite-level pass/fail gates."""

    minimum_success_rate: float | None = None
    maximum_p95_latency_ms: float | None = None
    maximum_cost_per_success_usd: float | None = None
    require_policy_pass: bool = False
    require_valid_json_rate: float | None = None
    minimum_tool_accuracy: float | None = None
    maximum_timeout_rate: float | None = None


class ReplacementConfig(_Strict):
    """Baseline-vs-candidate replacement thresholds."""

    baseline: str
    candidates: list[str]
    maximum_quality_drop: float = 0.05
    minimum_cost_reduction: float = 0.20
    maximum_latency_ms: float | None = None
    minimum_reliability: float | None = None


class CascadeConfig(_Strict):
    """First-stage + escalation configuration for cascade mode."""

    first_stage: str
    escalation_model: str
    conditions: list[CascadeCondition] = Field(default_factory=lambda: [CascadeCondition.EVALUATOR_FAILURE])
    low_score_threshold: float = 0.5
    low_confidence_threshold: float = 0.5
    escalate_tags: list[str] = Field(default_factory=list)


class ExecutionConfig(_Strict):
    """How the suite runs."""

    mode: ExecutionMode | None = None
    repetitions: int = 1
    concurrency: int = 1
    timeout_seconds: float = 60.0
    retries: int = 0
    store_raw_outputs: bool = True
    seed: int | None = None

    @field_validator("repetitions", "concurrency")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @field_validator("retries")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be >= 0")
        return value


class PrivacyConfig(_Strict):
    """Privacy and data-handling behavior for the suite."""

    allow_hosted_providers: bool = False
    redact_inputs_in_reports: bool = False
    store_raw_outputs: bool = True


class ScoringConfig(_Strict):
    """Scoring / economics configuration."""

    cost_mode: CostMode = CostMode.ZERO_MARGINAL
    compute_profile: ComputeCostProfile | None = None


class BenchmarkSuite(_Strict):
    """A complete, self-contained benchmark definition."""

    name: str
    version: str = "1.0"
    description: str = ""
    workflow: str = "generic"
    baseline_model: str | None = None
    models: list[ModelCandidate]
    cases: list[BenchmarkCase]
    evaluators: list[EvaluatorSpec] = Field(default_factory=list)
    constraints: Constraints = Field(default_factory=Constraints)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    cascade: CascadeConfig | None = None
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    replacement: ReplacementConfig | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_by_alias(self, alias: str) -> ModelCandidate | None:
        for model in self.models:
            if model.alias == alias:
                return model
        return None

    def effective_evaluators(self, case: BenchmarkCase) -> list[EvaluatorSpec]:
        """Case-level evaluators override suite-level ones; else fall back to suite."""
        return case.evaluators if case.evaluators else self.evaluators
