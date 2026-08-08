"""Strict schema for private local evaluation datasets."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CASES = 10_000
MAX_MESSAGES = 100
MAX_TEXT_LENGTH = 65_536


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class PrivacyClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"
    REGULATED = "regulated"


class DatasetMessage(_Strict):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    name: str | None = Field(default=None, max_length=256)


class ExpectedToolCall(_Strict):
    name: str = Field(min_length=1, max_length=256)
    arguments: dict[str, Any] = Field(default_factory=dict)


class DatasetProvenance(_Strict):
    source: str = Field(default="local", min_length=1, max_length=512)
    collection_method: str = Field(default="manual", min_length=1, max_length=256)
    source_version: str | None = Field(default=None, max_length=128)
    license: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2048)


class DatasetCase(_Strict):
    case_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    input_messages: list[DatasetMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    expected_output: Any | None = None
    reference_answer: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    evaluator_config: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    rubric: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list, max_length=100)
    expected_policy_result: str | None = Field(default=None, max_length=256)
    expected_citation_behavior: str | None = Field(default=None, max_length=2048)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    tags: list[str] = Field(default_factory=list, max_length=100)
    workload: str = Field(default="generic", min_length=1, max_length=256)
    human_outcome_label: str | None = Field(default=None, max_length=256)
    privacy_classification: PrivacyClassification | None = None
    source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provenance: DatasetProvenance = Field(default_factory=DatasetProvenance)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, tags: list[str]) -> list[str]:
        if any(not tag or len(tag) > 128 for tag in tags):
            raise ValueError("tags must be non-empty and at most 128 characters")
        return sorted(set(tags))


class EvaluationDataset(_Strict):
    schema_version: Literal["modelswapbench.dataset.v1"] = "modelswapbench.dataset.v1"
    dataset_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    name: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=4096)
    dataset_version: str = Field(default="1.0", min_length=1, max_length=128)
    updated_on: date = Field(default_factory=date.today)
    privacy_classification: PrivacyClassification = PrivacyClassification.UNKNOWN
    provenance: DatasetProvenance = Field(default_factory=DatasetProvenance)
    cases: list[DatasetCase] = Field(min_length=1, max_length=MAX_CASES)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> EvaluationDataset:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for case in self.cases:
            if case.case_id in seen:
                duplicates.add(case.case_id)
            seen.add(case.case_id)
        if duplicates:
            raise ValueError(f"duplicate case IDs: {', '.join(sorted(duplicates))}")
        return self

    def stable_copy(self, *, cases: list[DatasetCase] | None = None) -> EvaluationDataset:
        payload = self.model_dump(mode="json")
        payload["cases"] = [case.model_dump(mode="json") for case in (cases if cases is not None else self.cases)]
        return EvaluationDataset.model_validate(payload)
