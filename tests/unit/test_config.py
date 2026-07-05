from __future__ import annotations

import pytest

from model_swap_bench.config import build_suite, load_suite, schema_json
from model_swap_bench.errors import ConfigError, ValidationError
from tests.conftest import make_suite_dict


def test_valid_suite_builds() -> None:
    suite = build_suite(make_suite_dict())
    assert suite.name == "test-suite"
    assert len(suite.models) == 2
    assert suite.model_by_alias("candidate") is not None


def test_unknown_provider_rejected() -> None:
    d = make_suite_dict()
    d["models"][0]["provider"] = "not-a-provider"
    with pytest.raises(ValidationError):
        build_suite(d)


def test_duplicate_model_alias_rejected() -> None:
    d = make_suite_dict()
    d["models"][1]["alias"] = "baseline"
    with pytest.raises(ValidationError, match="duplicate model alias"):
        build_suite(d)


def test_duplicate_case_id_rejected() -> None:
    d = make_suite_dict()
    d["cases"][1]["id"] = "c1"
    with pytest.raises(ValidationError, match="duplicate case id"):
        build_suite(d)


def test_baseline_must_exist() -> None:
    d = make_suite_dict()
    d["baseline_model"] = "ghost"
    with pytest.raises(ValidationError, match="baseline_model"):
        build_suite(d)


def test_unknown_evaluator_rejected() -> None:
    d = make_suite_dict()
    d["evaluators"] = ["not_an_evaluator"]
    with pytest.raises(ValidationError, match="unknown evaluator"):
        build_suite(d)


def test_replacement_candidate_must_exist() -> None:
    d = make_suite_dict()
    d["replacement"]["candidates"] = ["ghost"]
    with pytest.raises(ValidationError):
        build_suite(d)


def test_extra_key_rejected() -> None:
    d = make_suite_dict()
    d["not_a_field"] = 1
    with pytest.raises(ValidationError):
        build_suite(d)


def test_load_missing_file() -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_suite("does-not-exist.yaml")


def test_schema_generation() -> None:
    text = schema_json()
    assert "BenchmarkSuite" in text or "properties" in text


def test_evaluator_alias_coercion() -> None:
    d = make_suite_dict()
    d["cases"][0]["evaluators"] = ["forbidden_content"]
    suite = build_suite(d)
    assert suite.cases[0].evaluators[0].name == "forbidden_content"
