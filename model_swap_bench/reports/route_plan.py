"""Model Routing Plan generation.

The plan is intentionally offline-first. It consumes per-task comparison data
and produces a deterministic migration plan across candidate, baseline, review,
and escalation routes.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench._version import __version__
from model_swap_bench.errors import ConfigError
from model_swap_bench.reports.exit_report import _audit_event_hash

DEFAULT_MIN_QUALITY_RETENTION = Decimal("80")
DEFAULT_MAX_LATENCY_INCREASE = Decimal("50")
DEFAULT_MIN_COST_REDUCTION = Decimal("20")
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_TASKS = 10_000
MAX_METRIC_VALUE = Decimal("1e9")
MIN_NONZERO_METRIC_VALUE = Decimal("1e-9")
MAX_METRIC_DIGITS = 50
RISK_PROFILES = frozenset({"low", "medium", "high", "regulated"})
BLOCKED_RISK_TERMS = frozenset(
    {
        "legal",
        "medical",
        "financial",
        "regulated",
        "safety-critical",
        "security incident",
    }
)
REVIEW_TERMS = frozenset({"customer facing", "angry", "escalated", "security sensitive", "external facing"})


class RouteDecision(str, Enum):
    """Supported per-task routing decisions."""

    CANDIDATE_MODEL = "candidate_model"
    BASELINE_MODEL = "baseline_model"
    HUMAN_REVIEW = "human_review"
    BLOCKED_OR_ESCALATE = "blocked_or_escalate"


class RiskLevel(str, Enum):
    """Normalized route-plan risk levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class Signal(str, Enum):
    """Human-readable metric signal."""

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class TaskRoutingInput(_Strict):
    """Per-task comparison input for a route plan."""

    task_id: str = Field(min_length=1, max_length=256)
    category: str = Field(default="uncategorized", min_length=1, max_length=256)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    baseline_score: Decimal | None = None
    candidate_score: Decimal | None = None
    baseline_latency: Decimal | None = None
    candidate_latency: Decimal | None = None
    baseline_cost: Decimal | None = None
    candidate_cost: Decimal | None = None
    policy_flags: list[str] = Field(default_factory=list, max_length=100)
    failure_flags: list[str] = Field(default_factory=list, max_length=100)
    notes: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def _validate_metrics_and_flags(self) -> TaskRoutingInput:
        for field_name in (
            "baseline_score",
            "candidate_score",
            "baseline_latency",
            "candidate_latency",
            "baseline_cost",
            "candidate_cost",
        ):
            value = getattr(self, field_name)
            if value is not None and (not value.is_finite() or value < 0):
                raise ValueError(f"{field_name} must be finite and non-negative")
            if value is not None and value > MAX_METRIC_VALUE:
                raise ValueError(f"{field_name} must not exceed {MAX_METRIC_VALUE}")
            if value is not None and value != 0 and value < MIN_NONZERO_METRIC_VALUE:
                raise ValueError(f"{field_name} must be zero or at least {MIN_NONZERO_METRIC_VALUE}")
            if value is not None and len(value.as_tuple().digits) > MAX_METRIC_DIGITS:
                raise ValueError(f"{field_name} must not exceed {MAX_METRIC_DIGITS} significant digits")
        if any(not flag or len(flag) > 256 for flag in [*self.policy_flags, *self.failure_flags]):
            raise ValueError("policy and failure flags must be non-empty and at most 256 characters")
        return self


class RoutingThresholds(_Strict):
    """Rule thresholds for task routing."""

    min_quality_retention_pct: Decimal = DEFAULT_MIN_QUALITY_RETENTION
    max_latency_increase_pct: Decimal = DEFAULT_MAX_LATENCY_INCREASE
    min_cost_reduction_pct: Decimal = DEFAULT_MIN_COST_REDUCTION
    high_risk_requires_review: bool = True
    blocked_categories: list[str] = Field(default_factory=lambda: sorted(BLOCKED_RISK_TERMS))

    @model_validator(mode="after")
    def _validate_thresholds(self) -> RoutingThresholds:
        for field_name in ("min_quality_retention_pct", "max_latency_increase_pct", "min_cost_reduction_pct"):
            value = getattr(self, field_name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be a finite, non-negative percentage")
        return self


class TaskRoutingDecision(_Strict):
    """Transparent rule output for one task."""

    task_id: str
    category: str
    route: RouteDecision
    reason: str
    quality_retention_pct: Decimal | None
    cost_reduction_pct: Decimal | None
    latency_delta_pct: Decimal | None
    risk_level: RiskLevel
    quality_signal: Signal
    cost_signal: Signal
    latency_signal: Signal
    policy_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RoutingSummary(_Strict):
    """Aggregate routing counts, percentages, and cost impact."""

    total_tasks: int
    candidate_model_tasks: int
    baseline_model_tasks: int
    human_review_tasks: int
    blocked_or_escalate_tasks: int
    candidate_model_pct: Decimal
    baseline_model_pct: Decimal
    human_review_pct: Decimal
    blocked_or_escalate_pct: Decimal
    baseline_total_estimated_cost: Decimal | None
    candidate_only_estimated_cost: Decimal | None
    routed_blended_estimated_cost: Decimal | None
    estimated_blended_savings_pct: Decimal | None


class ModelRoutingPlan(_Strict):
    """Full route-plan payload for Markdown or JSON rendering."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str
    workload: str
    baseline_model: str
    candidate_model: str
    risk_profile: str = "medium"
    source_path: str
    thresholds: RoutingThresholds
    summary: RoutingSummary
    task_decisions: list[TaskRoutingDecision]
    recommendation: str
    limitations: list[str] = Field(default_factory=list)
    cli_command: str | None = None
    package_version: str = __version__
    python_version: str = Field(default_factory=platform.python_version)
    platform: str = Field(default_factory=platform.platform)


class RouteAIMeterExport(_Strict):
    """Portable AIMeter OSS-style route-plan summary."""

    schema_version: str = "modelswapbench.route-plan.aimeter-export.v1"
    generated_at: datetime
    source: dict[str, Any]
    workload: str
    baseline_model: str
    candidate_model: str
    cost: dict[str, Any]
    routes: dict[str, int]
    quality: dict[str, Any]
    outcome: dict[str, Any]
    limitations: list[str]


class RouteAuditEvent(_Strict):
    """Portable AIAuditLog-style route-plan audit event."""

    schema_version: str = "modelswapbench.route-plan.audit-event.v1"
    event_id: str
    event_type: str
    event_time: datetime
    recorded_time: datetime
    timestamp: datetime
    actor: dict[str, Any]
    system_id: str
    run_id: str
    source: dict[str, Any]
    subject: dict[str, Any]
    action: str
    outcome: dict[str, Any]
    data: dict[str, Any]
    details: dict[str, Any]
    correlation: dict[str, Any]
    integrity: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str | None = None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ConfigError(f"invalid decimal value {value!r}") from exc
    if not parsed.is_finite():
        raise ConfigError(f"invalid decimal value {value!r}")
    return parsed


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator) * Decimal("100")


def quality_retention_pct(baseline_score: Decimal | None, candidate_score: Decimal | None) -> Decimal | None:
    if baseline_score is None or candidate_score is None or baseline_score <= 0:
        return None
    return _pct(candidate_score, baseline_score)


def cost_reduction_pct(baseline_cost: Decimal | None, candidate_cost: Decimal | None) -> Decimal | None:
    if baseline_cost is None or candidate_cost is None or baseline_cost <= 0:
        return None
    return ((baseline_cost - candidate_cost) / baseline_cost) * Decimal("100")


def latency_delta_pct(baseline_latency: Decimal | None, candidate_latency: Decimal | None) -> Decimal | None:
    if baseline_latency is None or candidate_latency is None or baseline_latency <= 0:
        return None
    return ((candidate_latency - baseline_latency) / baseline_latency) * Decimal("100")


def _normalized_terms(task: TaskRoutingInput) -> set[str]:
    values = [task.category, task.risk_level.value, *task.policy_flags, *task.failure_flags]
    terms: set[str] = set()
    for value in values:
        normalized = " ".join(part for part in re.split(r"[^a-z0-9]+", value.lower()) if part)
        if not normalized:
            continue
        terms.add(normalized)
        terms.update(part for part in normalized.split() if part in {"legal", "medical", "financial", "regulated"})
    if task.notes:
        notes = " ".join(part for part in re.split(r"[^a-z0-9]+", task.notes.lower()) if part)
        terms.update(
            " ".join(part for part in re.split(r"[^a-z0-9]+", term.lower()) if part)
            for term in BLOCKED_RISK_TERMS | REVIEW_TERMS
            if " ".join(part for part in re.split(r"[^a-z0-9]+", term.lower()) if part) in notes
        )
    return terms


def _signal(value: Decimal | None, threshold: Decimal, *, lower_is_better: bool = False) -> Signal:
    if value is None:
        return Signal.UNKNOWN
    if lower_is_better:
        return Signal.PASS if value <= threshold else Signal.FAIL
    return Signal.PASS if value >= threshold else Signal.FAIL


def _cost_signal(cost: Decimal | None, threshold: Decimal) -> Signal:
    if cost is None:
        return Signal.UNKNOWN
    if cost < 0:
        return Signal.FAIL
    if cost < threshold:
        return Signal.WARNING
    return Signal.PASS


def decide_task_route(
    task: TaskRoutingInput,
    thresholds: RoutingThresholds,
    *,
    risk_profile: str = "medium",
) -> TaskRoutingDecision:
    """Apply conservative routing rules for one task."""
    quality = quality_retention_pct(task.baseline_score, task.candidate_score)
    cost = cost_reduction_pct(task.baseline_cost, task.candidate_cost)
    latency = latency_delta_pct(task.baseline_latency, task.candidate_latency)
    quality_signal = _signal(quality, thresholds.min_quality_retention_pct)
    cost_signal = _cost_signal(cost, thresholds.min_cost_reduction_pct)
    latency_signal = _signal(latency, thresholds.max_latency_increase_pct, lower_is_better=True)
    warnings: list[str] = []
    policy_notes = list(task.policy_flags)
    normalized_profile = risk_profile.lower()
    if normalized_profile not in RISK_PROFILES:
        raise ConfigError(f"unknown risk profile {risk_profile!r}; choose low, medium, high, or regulated")
    terms = _normalized_terms(task) | {normalized_profile}
    blocked_categories = {
        " ".join(part for part in re.split(r"[^a-z0-9]+", item.lower()) if part) for item in thresholds.blocked_categories
    }

    if task.baseline_cost is None or task.candidate_cost is None:
        warnings.append("Cost is unknown; missing pricing was not treated as zero.")
    if quality is None:
        warnings.append("Quality retention is unknown.")
    if latency is None:
        warnings.append("Latency delta is unknown.")

    explicit_block = bool({"blocked", "policy blocked", "escalate", "requires escalation"} & terms)
    regulated_block = bool(blocked_categories & terms)
    insufficient = quality is None and latency is None and cost is None

    if explicit_block or regulated_block or insufficient:
        reason = "Task is blocked, regulated, escalated, or insufficiently evaluated."
        return TaskRoutingDecision(
            task_id=task.task_id,
            category=task.category,
            route=RouteDecision.BLOCKED_OR_ESCALATE,
            reason=reason,
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=task.risk_level,
            quality_signal=quality_signal,
            cost_signal=cost_signal,
            latency_signal=latency_signal,
            policy_notes=policy_notes,
            warnings=warnings,
        )

    if quality is not None and quality < thresholds.min_quality_retention_pct:
        return TaskRoutingDecision(
            task_id=task.task_id,
            category=task.category,
            route=RouteDecision.BASELINE_MODEL,
            reason="Quality retention is below the configured threshold.",
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=task.risk_level,
            quality_signal=quality_signal,
            cost_signal=cost_signal,
            latency_signal=latency_signal,
            policy_notes=policy_notes,
            warnings=warnings,
        )
    if task.failure_flags:
        return TaskRoutingDecision(
            task_id=task.task_id,
            category=task.category,
            route=RouteDecision.BASELINE_MODEL,
            reason="Candidate has failure flags that make baseline routing safer.",
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=task.risk_level,
            quality_signal=quality_signal,
            cost_signal=cost_signal,
            latency_signal=latency_signal,
            policy_notes=policy_notes,
            warnings=warnings,
        )
    if latency is not None and latency > thresholds.max_latency_increase_pct:
        return TaskRoutingDecision(
            task_id=task.task_id,
            category=task.category,
            route=RouteDecision.BASELINE_MODEL,
            reason="Candidate latency increase exceeds the configured threshold.",
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=task.risk_level,
            quality_signal=quality_signal,
            cost_signal=cost_signal,
            latency_signal=latency_signal,
            policy_notes=policy_notes,
            warnings=warnings,
        )

    borderline_quality = quality is None or quality < thresholds.min_quality_retention_pct + Decimal("10")
    weak_cost = cost is not None and cost < thresholds.min_cost_reduction_pct
    needs_review = (
        (task.risk_level is RiskLevel.HIGH or normalized_profile == "high")
        and thresholds.high_risk_requires_review
        or bool(REVIEW_TERMS & terms)
        or task.risk_level is RiskLevel.UNKNOWN
        or borderline_quality
        or weak_cost
        or (cost is None and task.risk_level is not RiskLevel.LOW)
    )
    if needs_review:
        return TaskRoutingDecision(
            task_id=task.task_id,
            category=task.category,
            route=RouteDecision.HUMAN_REVIEW,
            reason="Candidate may be usable, but risk, sensitivity, or borderline evidence requires review.",
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=task.risk_level,
            quality_signal=quality_signal,
            cost_signal=cost_signal,
            latency_signal=latency_signal,
            policy_notes=policy_notes,
            warnings=warnings,
        )

    return TaskRoutingDecision(
        task_id=task.task_id,
        category=task.category,
        route=RouteDecision.CANDIDATE_MODEL,
        reason="Quality, risk, latency, and cost evidence support candidate routing.",
        quality_retention_pct=quality,
        cost_reduction_pct=cost,
        latency_delta_pct=latency,
        risk_level=task.risk_level,
        quality_signal=quality_signal,
        cost_signal=cost_signal,
        latency_signal=latency_signal,
        policy_notes=policy_notes,
        warnings=warnings,
    )


def load_route_plan_input(path: Path) -> tuple[dict[str, Any], list[TaskRoutingInput]]:
    """Load route-plan input from JSON."""
    if not path.exists():
        raise ConfigError(f"route-plan input not found: {path}")
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise ConfigError(f"route-plan input exceeds the {MAX_INPUT_BYTES // (1024 * 1024)} MiB limit")
        source = path.read_text(encoding="utf-8")
    except ConfigError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"could not read route-plan input {path.name}: {exc}") from exc

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ConfigError(f"route-plan JSON contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_nonstandard_number(value: str) -> None:
        raise ConfigError(f"route-plan JSON contains non-finite number {value!r}")

    try:
        raw = json.loads(source, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_nonstandard_number)
    except ConfigError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ConfigError(f"could not parse route-plan JSON input {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("route-plan JSON input must be an object")
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        raise ConfigError("route-plan input must include a tasks list")
    if len(tasks) > MAX_TASKS:
        raise ConfigError(f"route-plan input exceeds the {MAX_TASKS} task limit")
    metadata = {key: value for key, value in raw.items() if key != "tasks"}
    parsed_tasks: list[TaskRoutingInput] = []
    seen_task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        try:
            parsed_task = TaskRoutingInput.model_validate(task)
        except PydanticValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
            raise ConfigError(f"invalid route-plan task at index {index}: {details}") from exc
        if parsed_task.task_id in seen_task_ids:
            raise ConfigError(f"duplicate route-plan task_id {parsed_task.task_id!r}")
        seen_task_ids.add(parsed_task.task_id)
        parsed_tasks.append(parsed_task)
    return metadata, parsed_tasks


def _summary(decisions: list[TaskRoutingDecision], tasks: list[TaskRoutingInput]) -> RoutingSummary:
    total = len(decisions)
    counts = {route: sum(1 for decision in decisions if decision.route is route) for route in RouteDecision}
    baseline_total: Decimal | None = Decimal("0")
    candidate_only: Decimal | None = Decimal("0")
    routed_blended: Decimal | None = Decimal("0")
    for task, decision in zip(tasks, decisions, strict=True):
        if task.baseline_cost is None:
            baseline_total = None
        elif baseline_total is not None:
            baseline_total += task.baseline_cost
        if task.candidate_cost is None:
            candidate_only = None
        elif candidate_only is not None:
            candidate_only += task.candidate_cost
        route_cost = task.candidate_cost if decision.route is RouteDecision.CANDIDATE_MODEL else task.baseline_cost
        if route_cost is None:
            routed_blended = None
        elif routed_blended is not None:
            routed_blended += route_cost
    savings = cost_reduction_pct(baseline_total, routed_blended)
    return RoutingSummary(
        total_tasks=total,
        candidate_model_tasks=counts[RouteDecision.CANDIDATE_MODEL],
        baseline_model_tasks=counts[RouteDecision.BASELINE_MODEL],
        human_review_tasks=counts[RouteDecision.HUMAN_REVIEW],
        blocked_or_escalate_tasks=counts[RouteDecision.BLOCKED_OR_ESCALATE],
        candidate_model_pct=_pct(Decimal(counts[RouteDecision.CANDIDATE_MODEL]), Decimal(total)) or Decimal("0"),
        baseline_model_pct=_pct(Decimal(counts[RouteDecision.BASELINE_MODEL]), Decimal(total)) or Decimal("0"),
        human_review_pct=_pct(Decimal(counts[RouteDecision.HUMAN_REVIEW]), Decimal(total)) or Decimal("0"),
        blocked_or_escalate_pct=_pct(Decimal(counts[RouteDecision.BLOCKED_OR_ESCALATE]), Decimal(total)) or Decimal("0"),
        baseline_total_estimated_cost=baseline_total,
        candidate_only_estimated_cost=candidate_only,
        routed_blended_estimated_cost=routed_blended,
        estimated_blended_savings_pct=savings,
    )


def _default_run_id(workload: str, source_path: Path) -> str:
    seed = f"{workload}|{source_path}|{datetime.now(UTC).date().isoformat()}"
    return f"route-plan-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _metadata_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError("route-plan generated_at metadata must be an ISO-8601 string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigError("route-plan generated_at metadata must be an ISO-8601 string") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_model_routing_plan(
    *,
    input_path: Path,
    baseline_model: str,
    candidate_model: str,
    workload: str | None = None,
    risk_profile: str = "medium",
    thresholds: RoutingThresholds | None = None,
    run_id: str | None = None,
    cli_command: str | None = None,
) -> ModelRoutingPlan:
    """Load input data and build a complete route plan."""
    normalized_risk = risk_profile.lower()
    if normalized_risk not in RISK_PROFILES:
        raise ConfigError(f"unknown risk profile {risk_profile!r}; choose low, medium, high, or regulated")
    metadata, tasks = load_route_plan_input(input_path)
    if not tasks:
        raise ConfigError("route-plan input must include at least one task")
    selected_thresholds = thresholds or RoutingThresholds()
    decisions = [decide_task_route(task, selected_thresholds, risk_profile=normalized_risk) for task in tasks]
    summary = _summary(decisions, tasks)
    selected_workload = workload or str(metadata.get("workload") or input_path.stem.replace("_", " ").replace("-", " "))
    selected_run_id = run_id or str(metadata.get("run_id") or _default_run_id(selected_workload, input_path))
    generated_at = _metadata_datetime(metadata.get("generated_at"))
    recommendation = _recommendation(summary)
    return ModelRoutingPlan(
        generated_at=generated_at or datetime.now(UTC),
        run_id=selected_run_id,
        workload=selected_workload,
        baseline_model=baseline_model or str(metadata.get("baseline_model") or "baseline"),
        candidate_model=candidate_model or str(metadata.get("candidate_model") or "candidate"),
        risk_profile=normalized_risk,
        source_path=str(input_path),
        thresholds=selected_thresholds,
        summary=summary,
        task_decisions=decisions,
        recommendation=recommendation,
        cli_command=cli_command,
        limitations=[
            "This plan is based on benchmark inputs and rule-based thresholds.",
            "Estimated cost is not invoice-confirmed.",
            "Projected savings are not realized savings.",
            "Blended cost uses baseline model cost as a proxy for review and escalation routes; human labor cost is excluded.",
            "Route decisions are not legal, regulatory, safety, security, or compliance guarantees.",
            "Human review may be required for high-risk or sensitive workflows.",
            "Model behavior can change across versions, providers, prompts, and runtime environments.",
            "Benchmark results do not prove universal safety.",
            "AIMeter and AIAuditLog outputs are portable file exports, not live runtime integrations.",
        ],
    )


def _recommendation(summary: RoutingSummary) -> str:
    if summary.blocked_or_escalate_tasks:
        return "Migrate only low-risk candidate-routed tasks first; escalate blocked tasks and review sensitive tasks before any rollout."
    if summary.human_review_tasks:
        return "Start with candidate-routed tasks and keep reviewed tasks behind human approval until more evidence is available."
    if summary.candidate_model_tasks == summary.total_tasks:
        return "Candidate routing appears suitable for this fixture; monitor drift and keep rollback paths available."
    return (
        "Use a mixed routing plan: candidate for passing tasks, baseline for failed gates, "
        "and continued evaluation before broader migration."
    )


def _fmt_decimal(value: Decimal | None, suffix: str = "") -> str:
    if value is None:
        return "Unknown"
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}{suffix}"


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "Unknown"
    return f"${value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def _decimal_string(value: Decimal | None, places: str | None = None) -> str | None:
    if value is None:
        return None
    if places is None:
        return str(value)
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _money_payload(value: Decimal | None) -> dict[str, str | bool | None]:
    return {
        "amount": _decimal_string(value, "0.0001"),
        "currency": "USD",
        "known": value is not None,
        "basis": "estimated" if value is not None else "unknown",
        "invoice_confirmed": False,
    }


def _md(value: object) -> str:
    return (
        str(value)
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("`", "&#96;")
    )


def render_model_routing_plan_markdown(plan: ModelRoutingPlan) -> str:
    """Render a practical Markdown migration plan."""
    summary = plan.summary
    lines = [
        "# Model Routing Plan",
        "",
        "## Executive Summary",
        "",
        plan.recommendation,
        "",
        "## Models Compared",
        "",
        f"- Baseline model/provider: `{_md(plan.baseline_model)}`",
        f"- Candidate model/provider: `{_md(plan.candidate_model)}`",
        f"- Date generated: {plan.generated_at.isoformat()}",
        f"- Benchmark input file or result source: `{_md(plan.source_path)}`",
        "",
        "## Workload",
        "",
        f"- Workload name: {_md(plan.workload)}",
        f"- Risk profile: {_md(plan.risk_profile)}",
        f"- Task count: {summary.total_tasks}",
        "",
        "## Routing Summary",
        "",
        f"- Candidate model: {_fmt_decimal(summary.candidate_model_pct, '%')} of tasks",
        f"- Baseline model: {_fmt_decimal(summary.baseline_model_pct, '%')} of tasks",
        f"- Human review: {_fmt_decimal(summary.human_review_pct, '%')} of tasks",
        f"- Blocked/escalate: {_fmt_decimal(summary.blocked_or_escalate_pct, '%')} of tasks",
        f"- Estimated blended savings: {_fmt_decimal(summary.estimated_blended_savings_pct, '%')}",
        "",
        "## Task Routing Table",
        "",
        "| Task | Category | Route | Risk | Quality | Cost | Latency | Reason |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for decision in plan.task_decisions:
        lines.append(
            "| "
            f"{_md(decision.task_id)} | {_md(decision.category)} | `{decision.route.value}` | {decision.risk_level.value} | "
            f"{_fmt_decimal(decision.quality_retention_pct, '%')} | {_fmt_decimal(decision.cost_reduction_pct, '%')} | "
            f"{_fmt_decimal(decision.latency_delta_pct, '%')} | {_md(decision.reason)} |"
        )
    lines.extend(
        [
            "",
            "## Estimated Blended Cost Impact",
            "",
            f"- Baseline total estimated cost: {_fmt_money(summary.baseline_total_estimated_cost)}",
            f"- Candidate-only estimated cost: {_fmt_money(summary.candidate_only_estimated_cost)}",
            f"- Routed/blended estimated cost: {_fmt_money(summary.routed_blended_estimated_cost)}",
            f"- Estimated savings vs baseline: {_fmt_decimal(summary.estimated_blended_savings_pct, '%')}",
            "- Caveat: estimated cost is not invoice-confirmed.",
            "- Caveat: projected savings are not realized savings.",
            "",
            "## Risk and Human Review",
            "",
        ]
    )
    for decision in plan.task_decisions:
        if decision.policy_notes or decision.warnings or decision.route in {RouteDecision.HUMAN_REVIEW, RouteDecision.BLOCKED_OR_ESCALATE}:
            notes = "; ".join([*decision.policy_notes, *decision.warnings]) or decision.reason
            lines.append(f"- `{_md(decision.task_id)}`: {_md(notes)}")
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            _md(plan.recommendation),
            "",
            "## Limitations",
            "",
            *[f"- {_md(limitation)}" for limitation in plan.limitations],
            "",
            "## Reproducibility",
            "",
            f"- CLI command used: `{_md(plan.cli_command or 'Unknown')}`",
            f"- Input file path: `{_md(plan.source_path)}`",
            f"- Run id: `{_md(plan.run_id)}`",
            f"- Package version: {plan.package_version}",
            f"- Timestamp: {plan.generated_at.isoformat()}",
            f"- Python version: {plan.python_version}",
            f"- Platform: {plan.platform}",
            "",
        ]
    )
    return "\n".join(lines)


def render_model_routing_plan_json(plan: ModelRoutingPlan, *, indent: int = 2) -> str:
    """Render a deterministic, parseable JSON route plan."""
    return json.dumps(plan.model_dump(mode="json"), indent=indent, default=str, sort_keys=True)


def build_route_aimeter_export(plan: ModelRoutingPlan) -> RouteAIMeterExport:
    """Build an AIMeter OSS-style export without adding a package dependency."""
    summary = plan.summary
    return RouteAIMeterExport(
        generated_at=plan.generated_at,
        source={
            "service": "modelswapbench",
            "component": "route-plan",
            "version": plan.package_version,
            "input_path": plan.source_path,
            "export_type": "aimeter-oss-style-route-cost-outcome-summary",
            "integration_mode": "offline-file-export",
        },
        workload=plan.workload,
        baseline_model=plan.baseline_model,
        candidate_model=plan.candidate_model,
        cost={
            "baseline_total_estimated_cost": _money_payload(summary.baseline_total_estimated_cost),
            "candidate_only_estimated_cost": _money_payload(summary.candidate_only_estimated_cost),
            "routed_blended_estimated_cost": _money_payload(summary.routed_blended_estimated_cost),
            "estimated_savings_vs_baseline_pct": _decimal_string(summary.estimated_blended_savings_pct, "0.01"),
            "projected_savings_realized": False,
        },
        routes={
            "candidate_model": summary.candidate_model_tasks,
            "baseline_model": summary.baseline_model_tasks,
            "human_review": summary.human_review_tasks,
            "blocked_or_escalate": summary.blocked_or_escalate_tasks,
        },
        quality={
            "tasks_passing_quality_gate": sum(1 for decision in plan.task_decisions if decision.quality_signal is Signal.PASS),
            "tasks_failing_quality_gate": sum(1 for decision in plan.task_decisions if decision.quality_signal is Signal.FAIL),
            "tasks_with_unknown_quality": sum(1 for decision in plan.task_decisions if decision.quality_signal is Signal.UNKNOWN),
        },
        outcome={
            "recommendation": plan.recommendation,
            "risk_profile": plan.risk_profile,
            "route_percentages": {
                "candidate_model": _decimal_string(summary.candidate_model_pct, "0.01"),
                "baseline_model": _decimal_string(summary.baseline_model_pct, "0.01"),
                "human_review": _decimal_string(summary.human_review_pct, "0.01"),
                "blocked_or_escalate": _decimal_string(summary.blocked_or_escalate_pct, "0.01"),
            },
        },
        limitations=plan.limitations
        + [
            "This is an AIMeter OSS-style portable export, not a live AIMeter runtime integration.",
            "Missing pricing is represented as unknown and is not treated as zero.",
        ],
    )


def render_route_aimeter_export_json(export: RouteAIMeterExport, *, indent: int = 2) -> str:
    """Render an AIMeter OSS-style route export as JSON."""
    return json.dumps(export.model_dump(mode="json"), indent=indent, default=str, sort_keys=True)


def build_route_audit_events(
    plan: ModelRoutingPlan,
    *,
    system_id: str = "modelswapbench",
    actor: str = "modelswapbench-cli",
    hash_chain: bool = True,
    include_aimeter_export_event: bool = False,
) -> list[RouteAuditEvent]:
    """Build AIAuditLog-style JSONL events for the route plan."""
    audit_actor = {"actor_id": actor, "actor_type": "system"}
    audit_source = {
        "service": "modelswapbench",
        "component": "route-plan",
        "version": plan.package_version,
        "integration_mode": "offline-file-export",
    }
    audit_subject = {
        "subject_type": "model_routing_plan",
        "subject_id": plan.run_id,
        "classification": "example-evidence",
    }
    audit_correlation = {"run_id": plan.run_id, "workflow_id": "model-routing-plan"}
    event_specs: list[tuple[str, str, str, dict[str, Any]]] = [
        ("route_plan_started", "start", "Model routing plan generation started.", {"workload": plan.workload}),
        ("route_plan_input_loaded", "load", "Route-plan input loaded.", {"input_path": plan.source_path}),
        (
            "routing_thresholds_evaluated",
            "evaluate",
            "Routing thresholds evaluated against task results.",
            plan.thresholds.model_dump(mode="json"),
        ),
    ]
    event_specs.extend(
        (
            "task_route_decision_recorded",
            "record",
            decision.route.value,
            {
                "task_id": decision.task_id,
                "route": decision.route.value,
                "reason": decision.reason,
                "risk_level": decision.risk_level.value,
            },
        )
        for decision in plan.task_decisions
    )
    event_specs.append(
        (
            "route_plan_generated",
            "generate",
            "Model Routing Plan generated.",
            {"routes": build_route_aimeter_export(plan).routes, "limitations_count": len(plan.limitations)},
        )
    )
    if include_aimeter_export_event:
        event_specs.append(
            (
                "aimeter_route_export_generated",
                "export",
                "AIMeter OSS-style route export generated.",
                {"export_type": "aimeter-oss-style-route-cost-outcome-summary"},
            )
        )

    previous_hash: str | None = None
    events = []
    for sequence, (event_type, action, reason, details) in enumerate(event_specs, start=1):
        event = RouteAuditEvent(
            event_id=f"{plan.run_id}-{sequence:04d}",
            event_type=event_type,
            event_time=plan.generated_at,
            recorded_time=plan.generated_at,
            timestamp=plan.generated_at,
            actor=audit_actor,
            system_id=system_id,
            run_id=plan.run_id,
            source=audit_source,
            subject=audit_subject,
            action=action,
            outcome={"status": "success", "code": "COMPLETED", "reason": reason},
            data=details,
            details=details,
            correlation=audit_correlation,
            integrity={"sequence": sequence, "digest_algorithm": "sha256", "chain_algorithm": "sha256"} if hash_chain else {},
            previous_hash=previous_hash if hash_chain else None,
        )
        if hash_chain:
            event.integrity["previous_event_digest"] = previous_hash
            dumped = event.model_dump(mode="json")
            event_hash = _audit_event_hash(dumped)
            event.integrity["event_digest"] = event_hash
            event.previous_hash = previous_hash
            event.event_hash = event_hash
            previous_hash = event_hash
        events.append(event)
    return events


def render_route_audit_events_jsonl(events: list[RouteAuditEvent]) -> str:
    """Render AIAuditLog-style route events as JSONL."""
    return "\n".join(json.dumps(event.model_dump(mode="json"), sort_keys=True, default=str) for event in events) + "\n"
