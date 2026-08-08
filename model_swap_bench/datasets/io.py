"""Duplicate-safe JSON/JSONL dataset loading and deterministic serialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.datasets.models import EvaluationDataset
from model_swap_bench.errors import ConfigError
from model_swap_bench.portable import (
    bounded_diagnostic,
    canonical_json,
    digest_value,
    load_json,
    load_json_file,
    pretty_json,
    read_bounded_text,
)

MAX_DATASET_BYTES = 20 * 1024 * 1024


def _build_dataset(payload: Any, source: str) -> EvaluationDataset:
    if not isinstance(payload, dict):
        raise ConfigError(f"{source} must contain a dataset object")
    try:
        dataset = EvaluationDataset.model_validate(payload)
    except PydanticValidationError as exc:
        raise ConfigError(f"dataset validation failed: {bounded_diagnostic(exc)}") from exc
    return dataset.stable_copy(cases=sorted(dataset.cases, key=lambda case: case.case_id))


def _load_jsonl(path: Path) -> EvaluationDataset:
    lines = read_bounded_text(path, max_bytes=MAX_DATASET_BYTES).splitlines()
    records = [load_json(line, source=f"{path.name}:{index}") for index, line in enumerate(lines, 1) if line.strip()]
    if not records:
        raise ConfigError("dataset JSONL is empty")
    metadata = records[0]
    if not isinstance(metadata, dict) or metadata.get("record_type") != "dataset_metadata":
        raise ConfigError("first JSONL record must have record_type='dataset_metadata'")
    metadata = {key: value for key, value in metadata.items() if key != "record_type"}
    cases: list[Any] = []
    for index, record in enumerate(records[1:], 2):
        if not isinstance(record, dict) or record.get("record_type") != "case":
            raise ConfigError(f"JSONL record {index} must have record_type='case'")
        cases.append({key: value for key, value in record.items() if key != "record_type"})
    metadata["cases"] = cases
    return _build_dataset(metadata, path.name)


def load_dataset(path: str | Path) -> EvaluationDataset:
    raw_path = str(path).strip()
    if raw_path.lower().startswith(("http://", "https://")):
        raise ConfigError("remote dataset loading is not supported")
    selected = Path(path)
    if selected.suffix.lower() == ".jsonl":
        return _load_jsonl(selected)
    if selected.suffix.lower() != ".json":
        raise ConfigError("dataset files must use .json or .jsonl")
    return _build_dataset(load_json_file(selected, max_bytes=MAX_DATASET_BYTES), selected.name)


def dataset_payload(dataset: EvaluationDataset, *, include_digest: bool = False) -> dict[str, Any]:
    payload = dataset.stable_copy().model_dump(mode="json")
    if include_digest:
        payload["digest"] = digest_value(payload)
    return payload


def dataset_digest(dataset: EvaluationDataset) -> str:
    return digest_value(dataset_payload(dataset))


def serialize_dataset(dataset: EvaluationDataset, *, fmt: str = "json") -> str:
    stable = dataset.stable_copy()
    if fmt == "json":
        return pretty_json(stable.model_dump(mode="json"))
    if fmt != "jsonl":
        raise ConfigError("dataset output format must be json or jsonl")
    payload = stable.model_dump(mode="json")
    cases = payload.pop("cases")
    lines = [canonical_json({"record_type": "dataset_metadata", **payload})]
    lines.extend(canonical_json({"record_type": "case", **case}) for case in cases)
    return "\n".join(lines) + "\n"


def write_dataset(dataset: EvaluationDataset, path: Path) -> None:
    fmt = "jsonl" if path.suffix.lower() == ".jsonl" else "json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_dataset(dataset, fmt=fmt), encoding="utf-8")
