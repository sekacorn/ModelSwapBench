"""Machine-readable baseline-versus-candidate CI regression gates."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

# Used only to serialize JUnit output; this module never parses XML input.
from xml.etree import ElementTree  # nosec B405

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.errors import ConfigError, ExitCode
from model_swap_bench.portable import bounded_diagnostic, load_json_file, pretty_json


class GateStatus(str, Enum):
    PASS = "pass"  # nosec B105
    REGRESSION = "regression"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class GateMetrics(_Strict):
    quality: float | None = None
    success_rate: float | None = None
    reliability: float | None = None
    valid_json_rate: float | None = None
    policy_pass_rate: float | None = None
    tool_call_accuracy: float | None = None
    citation_correctness: float | None = None
    p95_latency_ms: float | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    cost_per_successful_outcome_usd: Decimal | None = Field(default=None, ge=0)
    human_review_rate: float | None = None
    escalation_rate: float | None = None
    error_rate: float | None = None
    timeout_rate: float | None = None
    human_acceptance_rate: float | None = None
    business_success_rate: float | None = None

    @model_validator(mode="after")
    def _rates(self) -> GateMetrics:
        for name in (
            "quality",
            "success_rate",
            "reliability",
            "valid_json_rate",
            "policy_pass_rate",
            "tool_call_accuracy",
            "citation_correctness",
            "human_review_rate",
            "escalation_rate",
            "error_rate",
            "timeout_rate",
            "human_acceptance_rate",
            "business_success_rate",
        ):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        return self


class GateCaseEvidence(_Strict):
    case_id: str = Field(min_length=1, max_length=256)
    risk_level: str = Field(default="unknown", max_length=64)
    quality: float | None = Field(default=None, ge=0, le=1)
    success: bool | None = None
    policy_pass: bool | None = None
    business_success: bool | None = None


class GateArtifact(_Strict):
    schema_version: str = "modelswapbench.gate-artifact.v1"
    model: str = Field(min_length=1, max_length=512)
    run_id: str = Field(min_length=1, max_length=256)
    dataset_id: str = Field(min_length=1, max_length=256)
    dataset_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    sample_size: int = Field(ge=0)
    metrics: GateMetrics
    cases: list[GateCaseEvidence] = Field(default_factory=list, max_length=100_000)
    pricing_source: str | None = Field(default=None, max_length=512)
    pricing_status: str = Field(default="unknown", max_length=64)
    reproducibility: dict[str, Any] = Field(default_factory=dict)


class RiskGateThresholds(_Strict):
    minimum_quality: float | None = Field(default=None, ge=0, le=1)
    minimum_success_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_policy_pass_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_business_success_rate: float | None = Field(default=None, ge=0, le=1)


class GateThresholds(_Strict):
    minimum_sample_size: int = Field(default=20, ge=1)
    minimum_quality: float | None = Field(default=None, ge=0, le=1)
    maximum_quality_drop: float | None = Field(default=0.05, ge=0, le=1)
    minimum_success_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_success_rate_drop: float | None = Field(default=0.05, ge=0, le=1)
    minimum_reliability: float | None = Field(default=None, ge=0, le=1)
    minimum_valid_json_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_policy_pass_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_tool_call_accuracy: float | None = Field(default=None, ge=0, le=1)
    minimum_citation_correctness: float | None = Field(default=None, ge=0, le=1)
    maximum_p95_latency_ms: float | None = Field(default=None, ge=0)
    maximum_latency_increase_ratio: float | None = Field(default=None, ge=0)
    maximum_estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    minimum_cost_reduction_ratio: float | None = Field(default=None, ge=0, le=1)
    maximum_cost_per_successful_outcome_usd: Decimal | None = Field(default=None, ge=0)
    maximum_human_review_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_escalation_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_error_rate: float | None = Field(default=None, ge=0, le=1)
    maximum_timeout_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_human_acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    minimum_business_success_rate: float | None = Field(default=None, ge=0, le=1)
    risk_specific: dict[str, RiskGateThresholds] = Field(default_factory=dict)


class GateCheck(_Strict):
    name: str
    passed: bool
    category: str
    actual: str | float | int | bool | None
    threshold: str | float | int | bool | None
    detail: str


class GateResult(_Strict):
    schema_version: str = "modelswapbench.gate-result.v1"
    status: GateStatus
    baseline_model: str
    candidate_model: str
    sample_size: int
    checks: list[GateCheck]
    warnings: list[str]
    exit_code: int


def load_gate_artifact(path: Path) -> GateArtifact:
    try:
        return GateArtifact.model_validate(load_json_file(path, max_bytes=20 * 1024 * 1024))
    except PydanticValidationError as exc:
        raise ConfigError(f"invalid gate artifact {path.name}: {bounded_diagnostic(exc)}") from exc


def load_gate_thresholds(path: Path | None) -> GateThresholds:
    if path is None:
        return GateThresholds()
    try:
        return GateThresholds.model_validate(load_json_file(path))
    except PydanticValidationError as exc:
        raise ConfigError(f"invalid gate thresholds {path.name}: {bounded_diagnostic(exc)}") from exc


def evaluate_gate(baseline: GateArtifact, candidate: GateArtifact, thresholds: GateThresholds) -> GateResult:
    checks: list[GateCheck] = []
    warnings: list[str] = []
    insufficient = False

    def add(name: str, actual: Any, threshold: Any, passed: bool, detail: str, *, missing: bool = False) -> None:
        nonlocal insufficient
        category = "insufficient_evidence" if missing else "regression"
        if missing:
            insufficient = True
        checks.append(
            GateCheck(name=name, passed=passed, category="pass" if passed else category, actual=actual, threshold=threshold, detail=detail)
        )

    sample_ok = candidate.sample_size >= thresholds.minimum_sample_size
    add(
        "minimum_sample_size",
        candidate.sample_size,
        thresholds.minimum_sample_size,
        sample_ok,
        "candidate sample count",
        missing=not sample_ok,
    )
    if baseline.dataset_digest != candidate.dataset_digest:
        add("dataset_digest", candidate.dataset_digest, baseline.dataset_digest, False, "baseline and candidate datasets differ")
    else:
        add("dataset_digest", candidate.dataset_digest, baseline.dataset_digest, True, "same evaluation dataset")

    def minimum(name: str, actual: float | None, threshold: float | None) -> None:
        if threshold is None:
            return
        add(name, actual, threshold, actual is not None and actual >= threshold, "minimum required", missing=actual is None)

    def maximum(name: str, actual: Any, threshold: Any) -> None:
        if threshold is None:
            return
        add(
            name,
            None if actual is None else str(actual),
            str(threshold),
            actual is not None and actual <= threshold,
            "maximum allowed",
            missing=actual is None,
        )

    minimum("minimum_quality", candidate.metrics.quality, thresholds.minimum_quality)
    minimum("minimum_success_rate", candidate.metrics.success_rate, thresholds.minimum_success_rate)
    minimum("minimum_reliability", candidate.metrics.reliability, thresholds.minimum_reliability)
    minimum("minimum_valid_json_rate", candidate.metrics.valid_json_rate, thresholds.minimum_valid_json_rate)
    minimum("minimum_policy_pass_rate", candidate.metrics.policy_pass_rate, thresholds.minimum_policy_pass_rate)
    minimum("minimum_tool_call_accuracy", candidate.metrics.tool_call_accuracy, thresholds.minimum_tool_call_accuracy)
    minimum("minimum_citation_correctness", candidate.metrics.citation_correctness, thresholds.minimum_citation_correctness)
    minimum("minimum_human_acceptance_rate", candidate.metrics.human_acceptance_rate, thresholds.minimum_human_acceptance_rate)
    minimum("minimum_business_success_rate", candidate.metrics.business_success_rate, thresholds.minimum_business_success_rate)
    maximum("maximum_p95_latency_ms", candidate.metrics.p95_latency_ms, thresholds.maximum_p95_latency_ms)
    maximum("maximum_estimated_cost_usd", candidate.metrics.estimated_cost_usd, thresholds.maximum_estimated_cost_usd)
    maximum(
        "maximum_cost_per_successful_outcome_usd",
        candidate.metrics.cost_per_successful_outcome_usd,
        thresholds.maximum_cost_per_successful_outcome_usd,
    )
    maximum("maximum_human_review_rate", candidate.metrics.human_review_rate, thresholds.maximum_human_review_rate)
    maximum("maximum_escalation_rate", candidate.metrics.escalation_rate, thresholds.maximum_escalation_rate)
    maximum("maximum_error_rate", candidate.metrics.error_rate, thresholds.maximum_error_rate)
    maximum("maximum_timeout_rate", candidate.metrics.timeout_rate, thresholds.maximum_timeout_rate)

    if thresholds.maximum_quality_drop is not None:
        actual = None
        if baseline.metrics.quality is not None and candidate.metrics.quality is not None:
            actual = baseline.metrics.quality - candidate.metrics.quality
        maximum("maximum_quality_drop", actual, thresholds.maximum_quality_drop)
    if thresholds.maximum_success_rate_drop is not None:
        actual = None
        if baseline.metrics.success_rate is not None and candidate.metrics.success_rate is not None:
            actual = baseline.metrics.success_rate - candidate.metrics.success_rate
        maximum("maximum_success_rate_drop", actual, thresholds.maximum_success_rate_drop)
    if thresholds.maximum_latency_increase_ratio is not None:
        ratio = None
        if baseline.metrics.p95_latency_ms and candidate.metrics.p95_latency_ms is not None:
            ratio = (candidate.metrics.p95_latency_ms - baseline.metrics.p95_latency_ms) / baseline.metrics.p95_latency_ms
        maximum("maximum_latency_increase_ratio", ratio, thresholds.maximum_latency_increase_ratio)
    if thresholds.minimum_cost_reduction_ratio is not None:
        ratio = None
        if baseline.metrics.estimated_cost_usd and candidate.metrics.estimated_cost_usd is not None:
            ratio = float(
                (baseline.metrics.estimated_cost_usd - candidate.metrics.estimated_cost_usd) / baseline.metrics.estimated_cost_usd
            )
        minimum("minimum_cost_reduction_ratio", ratio, thresholds.minimum_cost_reduction_ratio)

    for risk, risk_thresholds in sorted(thresholds.risk_specific.items()):
        cases = [case for case in candidate.cases if case.risk_level == risk]
        if not cases:
            add(f"risk.{risk}.sample", None, 1, False, "no candidate cases for configured risk threshold", missing=True)
            continue
        qualities = [case.quality for case in cases if case.quality is not None]
        successes = [case.success for case in cases if case.success is not None]
        policies = [case.policy_pass for case in cases if case.policy_pass is not None]
        outcomes = [case.business_success for case in cases if case.business_success is not None]
        minimum(f"risk.{risk}.quality", sum(qualities) / len(qualities) if qualities else None, risk_thresholds.minimum_quality)
        minimum(
            f"risk.{risk}.success_rate",
            sum(bool(value) for value in successes) / len(successes) if successes else None,
            risk_thresholds.minimum_success_rate,
        )
        minimum(
            f"risk.{risk}.policy_pass_rate",
            sum(bool(value) for value in policies) / len(policies) if policies else None,
            risk_thresholds.minimum_policy_pass_rate,
        )
        minimum(
            f"risk.{risk}.business_success_rate",
            sum(bool(value) for value in outcomes) / len(outcomes) if outcomes else None,
            risk_thresholds.minimum_business_success_rate,
        )

    if candidate.pricing_status != "current":
        warnings.append("candidate pricing is estimated, stale, or unknown; cost gates depend on operator-supplied assumptions")
    failed = [check for check in checks if not check.passed]
    has_regression = any(check.category == "regression" for check in failed)
    status = GateStatus.PASS if not failed else GateStatus.REGRESSION if has_regression else GateStatus.INSUFFICIENT_EVIDENCE
    if status is GateStatus.PASS:
        exit_code = ExitCode.SUCCESS
    elif status is GateStatus.INSUFFICIENT_EVIDENCE:
        exit_code = ExitCode.PARTIAL_RUN
    else:
        exit_code = ExitCode.CONSTRAINTS_FAILED
    return GateResult(
        status=status,
        baseline_model=baseline.model,
        candidate_model=candidate.model,
        sample_size=candidate.sample_size,
        checks=checks,
        warnings=warnings,
        exit_code=int(exit_code),
    )


def render_gate_json(result: GateResult) -> str:
    return pretty_json(result.model_dump(mode="json"))


def render_gate_markdown(result: GateResult) -> str:
    lines = [
        "# ModelSwapBench Regression Gate",
        "",
        f"**Status:** {result.status.value}",
        "",
        f"Baseline: `{result.baseline_model}`  ",
        f"Candidate: `{result.candidate_model}`  ",
        f"Sample size: {result.sample_size}",
        "",
        "| Check | Result | Actual | Threshold | Detail |",
        "|---|---:|---:|---:|---|",
    ]
    for check in result.checks:
        detail = check.detail.replace("|", "&#124;").replace("\n", " ")
        lines.append(f"| {check.name} | {'PASS' if check.passed else 'FAIL'} | {check.actual} | {check.threshold} | {detail} |")
    if result.warnings:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in result.warnings]])
    lines.extend(
        [
            "",
            "Quality and cost gates are only as reliable as the benchmark dataset and pricing assumptions.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_gate_junit(result: GateResult) -> str:
    failures = sum(not check.passed for check in result.checks)
    suite = ElementTree.Element("testsuite", name="modelswapbench.gate", tests=str(len(result.checks)), failures=str(failures), errors="0")
    for check in result.checks:
        case = ElementTree.SubElement(suite, "testcase", classname="modelswapbench.gate", name=check.name)
        if not check.passed:
            failure = ElementTree.SubElement(case, "failure", message=check.category)
            failure.text = f"actual={check.actual}; threshold={check.threshold}; {check.detail}"
    return ElementTree.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def render_gate(result: GateResult, fmt: str) -> str:
    if fmt == "json":
        return render_gate_json(result)
    if fmt in {"markdown", "github"}:
        return render_gate_markdown(result)
    if fmt == "junit":
        return render_gate_junit(result)
    if fmt == "console":
        failed = sum(not check.passed for check in result.checks)
        return f"{result.status.value}: {failed} failed gate(s), sample_size={result.sample_size}\n"
    raise ConfigError("gate format must be console, json, markdown, github, or junit")
