"""Human feedback and business-outcome labels."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.errors import ConfigError
from model_swap_bench.portable import bounded_diagnostic, load_json, read_bounded_text


class OutcomeLabel(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CORRECTED = "corrected"
    ESCALATED = "escalated"
    CUSTOMER_RESOLVED = "customer_resolved"
    CUSTOMER_REOPENED = "customer_reopened"
    HUMAN_OVERRIDE = "human_override"
    UNSAFE = "unsafe"
    INCOMPLETE = "incomplete"
    OPERATIONALLY_UNUSABLE = "technically_correct_but_operationally_unusable"


class HumanOutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    case_id: str = Field(min_length=1, max_length=256)
    model_alias: str = Field(min_length=1, max_length=256)
    label: OutcomeLabel
    business_success: bool | None = None
    reviewer_role: str | None = Field(default=None, max_length=128)
    reviewer_id: str | None = Field(default=None, max_length=128)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2048)

    @field_validator("reviewer_id")
    @classmethod
    def _pseudonymous_reviewer(cls, value: str | None) -> str | None:
        if value is not None and "@" in value:
            raise ValueError("reviewer_id must be pseudonymous and must not be an email address")
        return value


class OutcomeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_size: int = 0
    human_acceptance_rate: float | None = None
    correction_rate: float | None = None
    escalation_rate: float | None = None
    reopen_rate: float | None = None
    override_rate: float | None = None
    business_success_rate: float | None = None
    cost_per_successful_outcome_usd: Decimal | None = None


class OutcomeComparison(BaseModel):
    """Candidate minus baseline human and business outcome differences."""

    model_config = ConfigDict(extra="forbid")
    baseline: OutcomeSummary
    candidate: OutcomeSummary
    human_acceptance_rate_difference: float | None
    correction_rate_difference: float | None
    escalation_rate_difference: float | None
    business_success_rate_difference: float | None
    cost_per_successful_outcome_difference_usd: Decimal | None


def load_outcomes_jsonl(path: Path) -> list[HumanOutcomeRecord]:
    records: list[HumanOutcomeRecord] = []
    for line_number, line in enumerate(read_bounded_text(path).splitlines(), 1):
        if not line.strip():
            continue
        payload = load_json(line, source=f"{path.name}:{line_number}")
        try:
            records.append(HumanOutcomeRecord.model_validate(payload))
        except PydanticValidationError as exc:
            raise ConfigError(f"invalid outcome record at line {line_number}: {bounded_diagnostic(exc)}") from exc
    return records


def aggregate_outcomes(records: list[HumanOutcomeRecord]) -> OutcomeSummary:
    total = len(records)
    if not total:
        return OutcomeSummary(sample_size=0)
    successes = [record for record in records if record.business_success is True]
    known_business = [record for record in records if record.business_success is not None]
    known_costs = [record.estimated_cost_usd for record in records if record.estimated_cost_usd is not None]
    labels = [record.label for record in records]

    def rate(count: int, denominator: int = total) -> float | None:
        return round(count / denominator, 4) if denominator else None

    cost_per_success = None
    if known_costs and len(known_costs) == total and successes:
        cost_per_success = sum(known_costs, Decimal("0")) / Decimal(len(successes))
    return OutcomeSummary(
        sample_size=total,
        human_acceptance_rate=rate(labels.count(OutcomeLabel.ACCEPTED)),
        correction_rate=rate(labels.count(OutcomeLabel.CORRECTED)),
        escalation_rate=rate(labels.count(OutcomeLabel.ESCALATED)),
        reopen_rate=rate(labels.count(OutcomeLabel.CUSTOMER_REOPENED)),
        override_rate=rate(labels.count(OutcomeLabel.HUMAN_OVERRIDE)),
        business_success_rate=rate(len(successes), len(known_business)),
        cost_per_successful_outcome_usd=cost_per_success,
    )


def compare_outcomes(baseline_records: list[HumanOutcomeRecord], candidate_records: list[HumanOutcomeRecord]) -> OutcomeComparison:
    baseline = aggregate_outcomes(baseline_records)
    candidate = aggregate_outcomes(candidate_records)

    def difference(candidate_value: float | None, baseline_value: float | None) -> float | None:
        if candidate_value is None or baseline_value is None:
            return None
        return round(candidate_value - baseline_value, 4)

    cost_difference = None
    if baseline.cost_per_successful_outcome_usd is not None and candidate.cost_per_successful_outcome_usd is not None:
        cost_difference = candidate.cost_per_successful_outcome_usd - baseline.cost_per_successful_outcome_usd
    return OutcomeComparison(
        baseline=baseline,
        candidate=candidate,
        human_acceptance_rate_difference=difference(candidate.human_acceptance_rate, baseline.human_acceptance_rate),
        correction_rate_difference=difference(candidate.correction_rate, baseline.correction_rate),
        escalation_rate_difference=difference(candidate.escalation_rate, baseline.escalation_rate),
        business_success_rate_difference=difference(candidate.business_success_rate, baseline.business_success_rate),
        cost_per_successful_outcome_difference_usd=cost_difference,
    )
