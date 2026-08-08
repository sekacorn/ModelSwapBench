from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from model_swap_bench.datasets.io import dataset_digest, load_dataset, serialize_dataset, write_dataset
from model_swap_bench.datasets.models import DatasetCase, DatasetMessage, EvaluationDataset
from model_swap_bench.datasets.operations import create_dataset, inspect_dataset, redact_dataset, split_dataset
from model_swap_bench.errors import ConfigError, SecurityError
from model_swap_bench.portable import bounded_diagnostic, ensure_distinct_paths, load_json, read_bounded_text


def _dataset() -> EvaluationDataset:
    return EvaluationDataset(
        dataset_id="private-support",
        name="Private support evaluation",
        privacy_classification="confidential",
        cases=[
            DatasetCase(
                case_id="case-b",
                input_messages=[DatasetMessage(role="user", content="Call +1 202 555 0100 using token sk-ABCDEFGHIJKLMNOP")],
                tags=["support", "private", "support"],
            ),
            DatasetCase(
                case_id="case-a",
                input_messages=[DatasetMessage(role="user", content="Reply to fixture-user@example.invalid")],
                expected_policy_result="allowed",
            ),
        ],
    )


def test_dataset_json_and_jsonl_are_stable_and_round_trip(tmp_path: Path) -> None:
    dataset = _dataset()
    json_path = tmp_path / "dataset.json"
    jsonl_path = tmp_path / "dataset.jsonl"
    write_dataset(dataset, json_path)
    write_dataset(dataset, jsonl_path)

    loaded_json = load_dataset(json_path)
    loaded_jsonl = load_dataset(jsonl_path)
    assert [case.case_id for case in loaded_json.cases] == ["case-a", "case-b"]
    assert dataset_digest(loaded_json) == dataset_digest(loaded_jsonl)
    assert serialize_dataset(loaded_json) == serialize_dataset(loaded_json)
    assert '"record_type":"dataset_metadata"' in serialize_dataset(loaded_json, fmt="jsonl")
    assert inspect_dataset(loaded_json)["case_count"] == 2


def test_dataset_duplicate_keys_ids_and_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="duplicate key"):
        load_json('{"dataset_id":"one","dataset_id":"two"}')
    with pytest.raises(ValidationError, match="duplicate case IDs"):
        EvaluationDataset(dataset_id="x", name="x", cases=[_dataset().cases[0], _dataset().cases[0]])

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"record_type":"case"}\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="first JSONL record"):
        load_dataset(bad)
    bad.write_text("\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load_dataset(bad)
    with pytest.raises(ConfigError, match="remote"):
        load_dataset("https://example.invalid/dataset.json")
    with pytest.raises(ConfigError, match="must use"):
        load_dataset(tmp_path / "dataset.yaml")
    with pytest.raises(ConfigError, match="format"):
        serialize_dataset(_dataset(), fmt="yaml")


def test_dataset_split_redaction_and_creation_are_deterministic() -> None:
    dataset = _dataset()
    train, evaluation = split_dataset(dataset, train_percent=50, test_percent=50)
    again = split_dataset(dataset, train_percent=50, test_percent=50)
    assert train == again[0]
    assert evaluation == again[1]
    assert {case.case_id for case in train.cases}.isdisjoint(case.case_id for case in evaluation.cases)
    assert "generalization" not in serialize_dataset(train).lower()

    redacted = redact_dataset(dataset)
    rendered = serialize_dataset(redacted)
    assert "fixture-user" not in rendered
    assert "sk-ABCDEFGHIJKLMNOP" not in rendered
    assert "[redacted-email]" in rendered
    assert all(case.source_hash for case in redacted.cases)
    assert create_dataset(dataset_id="new", name="New").cases[0].case_id == "example-case"

    with pytest.raises(ConfigError, match="sum to 100"):
        split_dataset(dataset, train_percent=70, test_percent=20)
    with pytest.raises(ConfigError, match="at least two"):
        split_dataset(create_dataset(dataset_id="one", name="One"), train_percent=80, test_percent=20)


def test_bounded_and_symlink_safe_file_helpers(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"value": "x"}), encoding="utf-8")
    assert "value" in read_bounded_text(source)
    with pytest.raises(ConfigError, match="exceeds"):
        read_bounded_text(source, max_bytes=1)
    with pytest.raises(ConfigError, match="not found"):
        read_bounded_text(tmp_path / "missing")
    with pytest.raises(SecurityError, match="overwrite"):
        ensure_distinct_paths(source, source)

    link_target = tmp_path / "link-target.json"
    link_target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(link_target)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(SecurityError, match="symbolic-link"):
        read_bounded_text(link)
    with pytest.raises(SecurityError, match="symbolic-link output"):
        ensure_distinct_paths(source, link)
    assert len(bounded_diagnostic("x" * 10_000)) < 4200
    assert "truncated" in bounded_diagnostic("x" * 10_000)
