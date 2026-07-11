"""AI Vendor Exit Report generation.

The report is intentionally offline-first. It consumes benchmark summaries or
JSONL fixture rows and produces a rule-based decision with transparent caveats.
"""

from __future__ import annotations

import json
import platform
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model_swap_bench._version import __version__
from model_swap_bench.errors import ConfigError

DEFAULT_MIN_QUALITY_RETENTION = Decimal("80")
DEFAULT_MAX_LATENCY_INCREASE = Decimal("50")
DEFAULT_MIN_COST_REDUCTION = Decimal("20")
MIN_EVIDENCE_SAMPLES = 3
MAX_FAILURE_RATE = Decimal("25")
RISK_PROFILES = frozenset({"low", "medium", "high", "regulated"})


class ExitDecision(str, Enum):
    """Supported high-level exit-report decisions."""

    ACCEPTABLE = "Candidate acceptable"
    HUMAN_REVIEW = "Candidate acceptable with human review"
    NOT_RECOMMENDED = "Candidate not recommended"
    INSUFFICIENT = "Insufficient evidence"


class RiskLevel(str, Enum):
    """Operational risk levels surfaced to non-specialist readers."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    UNKNOWN = "Unknown"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelIdentity(_Strict):
    """A provider/model pair plus a human-friendly label."""

    provider: str
    model: str
    label: str = ""

    @property
    def display_name(self) -> str:
        label = self.label or f"{self.provider}:{self.model}"
        return label

    @property
    def identifier(self) -> str:
        return f"{self.provider}:{self.model}"

    def matches(self, value: str) -> bool:
        normalized = value.strip().lower()
        return normalized in {self.identifier.lower(), self.model.lower(), self.display_name.lower()}


class BenchmarkSummary(_Strict):
    """Aggregated benchmark metrics for one model."""

    model: ModelIdentity
    score: Decimal | None = None
    average_latency_ms: Decimal | None = None
    estimated_cost_usd: Decimal | None = None
    sample_count: int = 0
    failure_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _coerce_flat_identity(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "model" in value and isinstance(value["model"], dict):
            return value
        provider = value.get("provider")
        model = value.get("model")
        if provider is not None and model is not None:
            copied = dict(value)
            copied["model"] = {"provider": str(provider), "model": str(model), "label": str(value.get("label") or model)}
            copied.pop("provider", None)
            copied.pop("label", None)
            return copied
        return value

    @property
    def failure_rate_pct(self) -> Decimal | None:
        if self.sample_count <= 0:
            return None
        return (Decimal(self.failure_count) / Decimal(self.sample_count)) * Decimal("100")


class ExitReportThresholds(_Strict):
    """Rule thresholds for the exit decision."""

    min_quality_retention_pct: Decimal = DEFAULT_MIN_QUALITY_RETENTION
    max_latency_increase_pct: Decimal = DEFAULT_MAX_LATENCY_INCREASE
    min_cost_reduction_pct: Decimal = DEFAULT_MIN_COST_REDUCTION

    @model_validator(mode="after")
    def _validate_thresholds(self) -> ExitReportThresholds:
        for field_name in ("min_quality_retention_pct", "max_latency_increase_pct", "min_cost_reduction_pct"):
            value = getattr(self, field_name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{field_name} must be a finite, non-negative percentage")
        return self


class ExitReportDecision(_Strict):
    """Transparent rule output for a candidate replacement."""

    decision: ExitDecision
    quality_retention_pct: Decimal | None = None
    cost_reduction_pct: Decimal | None = None
    latency_delta_pct: Decimal | None = None
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendation: str


class VendorExitReport(_Strict):
    """Full report payload for Markdown or JSON rendering."""

    title: str = "AI Vendor Exit Report"
    workload: str
    risk_profile: str = "medium"
    source_path: str
    baseline: BenchmarkSummary
    candidate: BenchmarkSummary
    thresholds: ExitReportThresholds
    decision: ExitReportDecision
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cli_command: str | None = None
    package_version: str = __version__
    python_version: str = Field(default_factory=platform.python_version)
    platform: str = Field(default_factory=platform.platform)
    limitations: list[str] = Field(default_factory=list)


def parse_identity(value: str) -> ModelIdentity:
    """Parse ``provider:model`` into a model identity."""
    if ":" in value:
        provider, model = value.split(":", 1)
        return ModelIdentity(provider=provider.strip(), model=model.strip(), label=value.strip())
    return ModelIdentity(provider="unknown", model=value.strip(), label=value.strip())


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
    """Return candidate quality as a percentage of baseline quality."""
    if baseline_score is None or candidate_score is None or baseline_score <= 0:
        return None
    return _pct(candidate_score, baseline_score)


def cost_reduction_pct(baseline_cost: Decimal | None, candidate_cost: Decimal | None) -> Decimal | None:
    """Return cost reduction percentage; missing cost stays unknown."""
    if baseline_cost is None or candidate_cost is None or baseline_cost <= 0:
        return None
    return ((baseline_cost - candidate_cost) / baseline_cost) * Decimal("100")


def latency_delta_pct(baseline_latency: Decimal | None, candidate_latency: Decimal | None) -> Decimal | None:
    """Return latency increase percentage. Negative means candidate is faster."""
    if baseline_latency is None or candidate_latency is None or baseline_latency <= 0:
        return None
    return ((candidate_latency - baseline_latency) / baseline_latency) * Decimal("100")


def _risk_level(risk_profile: str, baseline: BenchmarkSummary, candidate: BenchmarkSummary) -> tuple[RiskLevel, str]:
    profile = risk_profile.lower()
    if profile in {"regulated", "high"}:
        return RiskLevel.HIGH, "The workload is marked high-risk or regulated."
    if profile == "low":
        if candidate.failure_count == 0:
            return RiskLevel.LOW, "The workload is low-risk and the candidate has no observed failures."
        return RiskLevel.MEDIUM, "The workload is low-risk, but candidate failures were observed."
    failure_rate = candidate.failure_rate_pct
    if failure_rate is None:
        return RiskLevel.UNKNOWN, "Failure rate is unknown because sample count is missing."
    if failure_rate > Decimal("10") or baseline.failure_count < candidate.failure_count:
        return RiskLevel.MEDIUM, "Candidate failures or reliability regression require review."
    return RiskLevel.MEDIUM, "Default medium risk profile; validate before migration."


def decide_exit(
    baseline: BenchmarkSummary,
    candidate: BenchmarkSummary,
    thresholds: ExitReportThresholds,
    *,
    risk_profile: str,
) -> ExitReportDecision:
    """Apply transparent exit-report rules."""
    if risk_profile.lower() not in RISK_PROFILES:
        raise ConfigError(f"unknown risk profile {risk_profile!r}; choose low, medium, high, or regulated")
    quality = quality_retention_pct(baseline.score, candidate.score)
    cost = cost_reduction_pct(baseline.estimated_cost_usd, candidate.estimated_cost_usd)
    latency = latency_delta_pct(baseline.average_latency_ms, candidate.average_latency_ms)
    risk, risk_reason = _risk_level(risk_profile, baseline, candidate)
    reasons = [risk_reason]
    warnings: list[str] = []

    if baseline.sample_count < MIN_EVIDENCE_SAMPLES or candidate.sample_count < MIN_EVIDENCE_SAMPLES:
        reasons.append(f"At least {MIN_EVIDENCE_SAMPLES} samples per model are recommended.")
        return ExitReportDecision(
            decision=ExitDecision.INSUFFICIENT,
            quality_retention_pct=quality,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=risk,
            reasons=reasons,
            recommendation="Run a larger evaluation set before migration.",
        )

    if quality is None:
        reasons.append("Quality retention is unknown because baseline or candidate score is missing or zero.")
        return ExitReportDecision(
            decision=ExitDecision.INSUFFICIENT,
            quality_retention_pct=None,
            cost_reduction_pct=cost,
            latency_delta_pct=latency,
            risk_level=risk,
            reasons=reasons,
            recommendation="Run a scored benchmark before migration.",
        )

    if cost is None:
        warnings.append("Cost is unknown; missing pricing was not treated as zero.")
        reasons.append("Cost reduction cannot be calculated from the provided data.")
        return ExitReportDecision(
            decision=ExitDecision.INSUFFICIENT,
            quality_retention_pct=quality,
            cost_reduction_pct=None,
            latency_delta_pct=latency,
            risk_level=risk,
            reasons=reasons,
            warnings=warnings,
            recommendation="Add estimated pricing before making a vendor-exit decision.",
        )

    if latency is None:
        warnings.append("Latency delta is unknown.")

    failure_rate = candidate.failure_rate_pct
    if quality < thresholds.min_quality_retention_pct:
        reasons.append("Quality retention is below the required threshold.")
        decision = ExitDecision.NOT_RECOMMENDED
        recommendation = "Keep the baseline model for this workload until quality improves."
    elif failure_rate is not None and failure_rate > MAX_FAILURE_RATE:
        reasons.append("Candidate failure rate is too high.")
        decision = ExitDecision.NOT_RECOMMENDED
        recommendation = "Keep the baseline model and investigate candidate failures."
    elif latency is not None and latency > thresholds.max_latency_increase_pct:
        reasons.append("Candidate latency increase exceeds the configured threshold.")
        decision = ExitDecision.NOT_RECOMMENDED
        recommendation = "Keep the baseline model for latency-sensitive paths."
    elif cost < thresholds.min_cost_reduction_pct and cost < Decimal("0"):
        reasons.append("Candidate is more expensive than the baseline.")
        decision = ExitDecision.NOT_RECOMMENDED
        recommendation = "Do not migrate unless there is a non-cost reason to accept higher spend."
    elif risk is RiskLevel.HIGH or risk_profile.lower() == "regulated":
        reasons.append("Quality passes, but the risk profile requires human review.")
        decision = ExitDecision.HUMAN_REVIEW
        recommendation = "Use candidate only after human review and policy approval for high-risk workflows."
    elif warnings or cost < thresholds.min_cost_reduction_pct:
        reasons.append("Core quality passes, but one non-critical warning or weak cost reduction remains.")
        decision = ExitDecision.HUMAN_REVIEW
        recommendation = "Use candidate model for bounded workflows with human review and monitoring."
    else:
        reasons.append("Quality, cost, latency, and risk gates passed.")
        decision = ExitDecision.ACCEPTABLE
        recommendation = "Use candidate model for low-risk internal workflows and monitor drift."

    return ExitReportDecision(
        decision=decision,
        quality_retention_pct=quality,
        cost_reduction_pct=cost,
        latency_delta_pct=latency,
        risk_level=risk,
        reasons=reasons,
        warnings=warnings,
        recommendation=recommendation,
    )


def load_exit_summaries(path: Path) -> tuple[str | None, list[BenchmarkSummary]]:
    """Load summaries from JSON or JSONL fixture data."""
    if not path.exists():
        raise ConfigError(f"exit-report input not found: {path}")
    if path.suffix.lower() == ".jsonl":
        return None, _load_jsonl(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return None, [BenchmarkSummary.model_validate(item) for item in raw]
    if not isinstance(raw, dict):
        raise ConfigError("exit-report JSON input must be an object or list")
    workload = raw.get("workload") if isinstance(raw.get("workload"), str) else None
    if "summaries" in raw:
        summaries = raw["summaries"]
    elif "models" in raw:
        summaries = raw["models"]
    elif "model_summaries" in raw:
        summaries = _summaries_from_run(raw)
    else:
        summaries = [raw[key] for key in ("baseline", "candidate") if key in raw]
    if not isinstance(summaries, list):
        raise ConfigError("exit-report summaries must be a list")
    return workload, [BenchmarkSummary.model_validate(item) for item in summaries]


def _summaries_from_run(raw: dict[str, Any]) -> list[dict[str, Any]]:
    converted = []
    for item in raw.get("model_summaries", []):
        converted.append(
            {
                "provider": item.get("provider", "unknown"),
                "model": item.get("model_alias", "unknown"),
                "label": item.get("model_alias", "unknown"),
                "score": item.get("quality_score"),
                "average_latency_ms": item.get("avg_latency_ms"),
                "estimated_cost_usd": item.get("total_cost_usd"),
                "sample_count": item.get("total_cases", 0),
                "failure_count": item.get("failed_cases", 0) + item.get("error_cases", 0) + item.get("timeout_cases", 0),
            }
        )
    return converted


def _load_jsonl(path: Path) -> list[BenchmarkSummary]:
    buckets: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        provider = str(row.get("provider") or "unknown")
        model = str(row.get("model") or row.get("label") or "unknown")
        label = str(row.get("label") or f"{provider}:{model}")
        key = f"{provider}:{model}:{label}"
        bucket = buckets.setdefault(
            key,
            {
                "provider": provider,
                "model": model,
                "label": label,
                "score_total": Decimal("0"),
                "score_count": 0,
                "latency_total": Decimal("0"),
                "latency_count": 0,
                "cost_total": None,
                "sample_count": 0,
                "failure_count": 0,
            },
        )
        bucket["sample_count"] += 1
        status = str(row.get("status", "success")).lower()
        if status not in {"success", "pass", "passed"}:
            bucket["failure_count"] += 1
        score = _decimal(row.get("score"))
        if score is not None:
            bucket["score_total"] += score
            bucket["score_count"] += 1
        latency = _decimal(row.get("latency_ms") if "latency_ms" in row else row.get("average_latency_ms"))
        if latency is not None:
            bucket["latency_total"] += latency
            bucket["latency_count"] += 1
        cost = _decimal(row.get("estimated_cost_usd"))
        if cost is not None:
            bucket["cost_total"] = (bucket["cost_total"] or Decimal("0")) + cost
        if "provider" not in row or ("model" not in row and "label" not in row):
            raise ConfigError(f"JSONL row {line_number} must include provider and model or label")
    summaries = []
    for bucket in buckets.values():
        score = None
        if bucket["score_count"]:
            score = bucket["score_total"] / Decimal(bucket["score_count"])
        latency = None
        if bucket["latency_count"]:
            latency = bucket["latency_total"] / Decimal(bucket["latency_count"])
        summaries.append(
            BenchmarkSummary(
                model=ModelIdentity(provider=bucket["provider"], model=bucket["model"], label=bucket["label"]),
                score=score,
                average_latency_ms=latency,
                estimated_cost_usd=bucket["cost_total"],
                sample_count=bucket["sample_count"],
                failure_count=bucket["failure_count"],
            )
        )
    return summaries


def select_summary(summaries: list[BenchmarkSummary], requested: str) -> BenchmarkSummary:
    """Find a requested model by provider:model, model, or label."""
    for summary in summaries:
        if summary.model.matches(requested):
            return summary
    available = ", ".join(s.model.identifier for s in summaries)
    raise ConfigError(f"model {requested!r} not found in exit-report input; available: {available}")


def build_exit_report(
    *,
    input_path: Path,
    baseline_ref: str,
    candidate_ref: str,
    title: str = "AI Vendor Exit Report",
    workload: str | None = None,
    risk_profile: str = "medium",
    thresholds: ExitReportThresholds | None = None,
    cli_command: str | None = None,
) -> VendorExitReport:
    """Load input data and build a complete exit report."""
    normalized_risk = risk_profile.lower()
    if normalized_risk not in RISK_PROFILES:
        raise ConfigError(f"unknown risk profile {risk_profile!r}; choose low, medium, high, or regulated")
    input_workload, summaries = load_exit_summaries(input_path)
    baseline = select_summary(summaries, baseline_ref)
    candidate = select_summary(summaries, candidate_ref)
    selected_thresholds = thresholds or ExitReportThresholds()
    decision = decide_exit(baseline, candidate, selected_thresholds, risk_profile=risk_profile)
    return VendorExitReport(
        title=title,
        workload=workload or input_workload or input_path.stem.replace("_", " ").replace("-", " "),
        risk_profile=normalized_risk,
        source_path=str(input_path),
        baseline=baseline,
        candidate=candidate,
        thresholds=selected_thresholds,
        decision=decision,
        cli_command=cli_command,
        limitations=[
            "This report is based on benchmark inputs and scoring configuration.",
            "Estimated cost is not invoice-confirmed.",
            "Projected savings are not realized savings.",
            "Passing this benchmark does not prove legal, regulatory, safety, or security compliance.",
            "Human review may still be required for high-risk workflows.",
            "Model behavior can change across versions, providers, prompts, and runtime environments.",
        ],
    )


def _fmt_decimal(value: Decimal | None, suffix: str = "") -> str:
    if value is None:
        return "Unknown"
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized}{suffix}"


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "Unknown"
    return f"${value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def _md(value: object) -> str:
    """Escape Markdown-significant HTML delimiters from user-controlled values."""
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_exit_report_markdown(report: VendorExitReport) -> str:
    """Render a CTO-friendly Markdown report."""
    d = report.decision
    baseline = report.baseline
    candidate = report.candidate
    quality_status = (
        "PASS"
        if d.quality_retention_pct is not None and d.quality_retention_pct >= report.thresholds.min_quality_retention_pct
        else "WARNING"
    )
    cost_status = (
        "PASS" if d.cost_reduction_pct is not None and d.cost_reduction_pct >= report.thresholds.min_cost_reduction_pct else "WARNING"
    )
    latency_status = "PASS"
    if d.latency_delta_pct is None or d.latency_delta_pct > report.thresholds.max_latency_increase_pct:
        latency_status = "WARNING"

    lines = [
        f"# {report.title}",
        "",
        "## Executive Summary",
        "",
        f"{d.decision.value}. {d.recommendation}",
        "",
        "## Models Compared",
        "",
        f"- Baseline model/provider: `{_md(baseline.model.identifier)}` ({_md(baseline.model.display_name)})",
        f"- Candidate model/provider: `{_md(candidate.model.identifier)}` ({_md(candidate.model.display_name)})",
        f"- Workload name: {_md(report.workload)}",
        f"- Date generated: {report.generated_at.isoformat()}",
        f"- Benchmark input file or result source: `{_md(report.source_path)}`",
        "",
        "## Decision",
        "",
        f"**{d.decision.value}**",
        "",
        "Reasons:",
        *[f"- {_md(reason)}" for reason in d.reasons],
    ]
    if d.warnings:
        lines.extend(["", "Warnings:", *[f"- {_md(warning)}" for warning in d.warnings]])
    lines.extend(
        [
            "",
            "## Quality",
            "",
            f"- Baseline score: {_fmt_decimal(baseline.score)}",
            f"- Candidate score: {_fmt_decimal(candidate.score)}",
            f"- Quality retention: {_fmt_decimal(d.quality_retention_pct, '%')}",
            f"- Threshold used: {_fmt_decimal(report.thresholds.min_quality_retention_pct, '%')}",
            f"- Result: {quality_status}",
            "",
            "## Cost",
            "",
            f"- Baseline estimated cost: {_fmt_money(baseline.estimated_cost_usd)}",
            f"- Candidate estimated cost: {_fmt_money(candidate.estimated_cost_usd)}",
            f"- Estimated cost difference: {_fmt_money(_cost_difference(baseline, candidate))}",
            f"- Estimated cost reduction: {_fmt_decimal(d.cost_reduction_pct, '%')}",
            "- Caveat: estimated cost is not invoice-confirmed.",
            "- Caveat: projected savings are not realized savings.",
            f"- Result: {cost_status}",
            "",
            "## Latency",
            "",
            f"- Baseline average latency: {_fmt_decimal(baseline.average_latency_ms, ' ms')}",
            f"- Candidate average latency: {_fmt_decimal(candidate.average_latency_ms, ' ms')}",
            f"- Latency delta: {_fmt_decimal(d.latency_delta_pct, '%')}",
            f"- Threshold used: {_fmt_decimal(report.thresholds.max_latency_increase_pct, '%')} maximum increase",
            f"- Result: {latency_status}",
            "",
            "## Risk",
            "",
            f"- Risk profile: {_md(report.risk_profile)}",
            f"- Operational risk level: {d.risk_level.value}",
            f"- Reason: {_md(d.reasons[0] if d.reasons else 'No risk reason provided.')}",
            "- Recommended use boundaries: start with bounded workflows, monitor drift, and keep rollback paths available.",
            "",
            "## Recommendation",
            "",
            _md(d.recommendation),
            "",
            "## Limitations",
            "",
            *[f"- {_md(limitation)}" for limitation in report.limitations],
            "",
            "## Reproducibility",
            "",
            f"- CLI command used: `{_md(report.cli_command or 'Unknown')}`",
            f"- Input file path: `{_md(report.source_path)}`",
            f"- Package version: {report.package_version}",
            f"- Timestamp: {report.generated_at.isoformat()}",
            f"- Python version: {report.python_version}",
            f"- Platform: {report.platform}",
            "",
        ]
    )
    return "\n".join(lines)


def _cost_difference(baseline: BenchmarkSummary, candidate: BenchmarkSummary) -> Decimal | None:
    if baseline.estimated_cost_usd is None or candidate.estimated_cost_usd is None:
        return None
    return candidate.estimated_cost_usd - baseline.estimated_cost_usd


def render_exit_report_json(report: VendorExitReport, *, indent: int = 2) -> str:
    """Render a machine-readable JSON exit report."""
    return json.dumps(report.model_dump(mode="json"), indent=indent, default=str)
