"""Deterministic private dataset creation, inspection, splitting, and redaction."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from model_swap_bench.datasets.io import dataset_digest
from model_swap_bench.datasets.models import (
    DatasetCase,
    DatasetMessage,
    DatasetProvenance,
    EvaluationDataset,
    PrivacyClassification,
    RiskLevel,
)
from model_swap_bench.errors import ConfigError
from model_swap_bench.portable import canonical_json
from model_swap_bench.security.redaction import redact_value

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")


def create_dataset(*, dataset_id: str, name: str) -> EvaluationDataset:
    return EvaluationDataset(
        dataset_id=dataset_id,
        name=name,
        description="Private local evaluation dataset. Replace this example before use.",
        updated_on=date.today(),
        privacy_classification=PrivacyClassification.INTERNAL,
        provenance=DatasetProvenance(source="local", collection_method="manual"),
        cases=[
            DatasetCase(
                case_id="example-case",
                input_messages=[DatasetMessage(role="user", content="Replace with a representative private workflow case.")],
                risk_level=RiskLevel.UNKNOWN,
                workload="generic",
                privacy_classification=PrivacyClassification.INTERNAL,
            )
        ],
    )


def inspect_dataset(dataset: EvaluationDataset) -> dict[str, Any]:
    classifications: dict[str, int] = {}
    risks: dict[str, int] = {}
    for case in dataset.cases:
        classification = (case.privacy_classification or dataset.privacy_classification).value
        classifications[classification] = classifications.get(classification, 0) + 1
        risks[case.risk_level.value] = risks.get(case.risk_level.value, 0) + 1
    return {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "dataset_version": dataset.dataset_version,
        "schema_version": dataset.schema_version,
        "case_count": len(dataset.cases),
        "privacy_classifications": dict(sorted(classifications.items())),
        "risk_levels": dict(sorted(risks.items())),
        "digest": dataset_digest(dataset),
    }


def split_dataset(
    dataset: EvaluationDataset, *, train_percent: int, test_percent: int, seed: str = "modelswapbench-dataset-split-v1"
) -> tuple[EvaluationDataset, EvaluationDataset]:
    if train_percent <= 0 or test_percent <= 0 or train_percent + test_percent != 100:
        raise ConfigError("train and test percentages must be positive and sum to 100")
    if len(dataset.cases) < 2:
        raise ConfigError("dataset split requires at least two cases")
    ranked = sorted(
        dataset.cases,
        key=lambda case: (hashlib.sha256(f"{seed}:{case.case_id}".encode()).hexdigest(), case.case_id),
    )
    train_count = max(1, min(len(ranked) - 1, round(len(ranked) * train_percent / 100)))
    train_cases = sorted(ranked[:train_count], key=lambda case: case.case_id)
    test_cases = sorted(ranked[train_count:], key=lambda case: case.case_id)
    train = dataset.stable_copy(cases=train_cases).model_copy(
        update={"dataset_id": f"{dataset.dataset_id}-train", "name": f"{dataset.name} (train)"}
    )
    test = dataset.stable_copy(cases=test_cases).model_copy(
        update={"dataset_id": f"{dataset.dataset_id}-test", "name": f"{dataset.name} (evaluation)"}
    )
    return train, test


def _redact_text(text: str) -> str:
    without_email = _EMAIL.sub("[redacted-email]", text)
    return _PHONE.sub(
        lambda match: "[redacted-phone]" if sum(character.isdigit() for character in match.group()) >= 10 else match.group(),
        without_email,
    )


def _redact_any(value: Any) -> Any:
    redacted = redact_value(value)
    if isinstance(redacted, str):
        return _redact_text(redacted)
    if isinstance(redacted, list):
        return [_redact_any(item) for item in redacted]
    if isinstance(redacted, dict):
        return {key: _redact_any(item) for key, item in redacted.items()}
    return redacted


def redact_dataset(dataset: EvaluationDataset) -> EvaluationDataset:
    source_hashes = {
        case.case_id: hashlib.sha256(canonical_json(case.model_dump(mode="json", exclude={"source_hash"})).encode("utf-8")).hexdigest()
        for case in dataset.cases
    }
    payload = _redact_any(dataset.model_dump(mode="json"))
    payload["privacy_classification"] = PrivacyClassification.INTERNAL.value
    for case in payload["cases"]:
        case["privacy_classification"] = PrivacyClassification.INTERNAL.value
        case["source_hash"] = source_hashes[case["case_id"]]
    return EvaluationDataset.model_validate(payload).stable_copy()
