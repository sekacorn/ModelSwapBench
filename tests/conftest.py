"""Shared test fixtures and helpers (all offline, deterministic)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from model_swap_bench.config import build_suite
from model_swap_bench.config.models import BenchmarkSuite


def make_suite_dict(**overrides: Any) -> dict[str, Any]:
    """A minimal, valid, fully-deterministic suite dict for tests."""
    base: dict[str, Any] = {
        "name": "test-suite",
        "version": "1.0",
        "baseline_model": "baseline",
        "models": [
            {
                "alias": "baseline",
                "provider": "deterministic",
                "model": "base",
                "deployment": "test",
                "estimated_input_cost_per_million": 5.0,
                "estimated_output_cost_per_million": 15.0,
                "metadata": {"strategy": "oracle", "latency_ms": 100},
            },
            {
                "alias": "candidate",
                "provider": "deterministic",
                "model": "cand",
                "deployment": "local",
                "metadata": {"strategy": "oracle", "latency_ms": 10},
            },
        ],
        "cases": [
            {"id": "c1", "input": {"message": "hi"}, "expected": {"category": "billing", "escalation_required": True}},
            {"id": "c2", "input": {"message": "yo"}, "expected": {"category": "refund", "escalation_required": False}},
        ],
        "evaluators": ["json_parse", "json_schema", "field_match"],
        "constraints": {"minimum_success_rate": 0.8, "require_valid_json_rate": 0.9},
        "replacement": {"baseline": "baseline", "candidates": ["candidate"], "maximum_quality_drop": 0.05, "minimum_cost_reduction": 0.2},
    }
    base.update(overrides)
    return base


@pytest.fixture
def suite() -> BenchmarkSuite:
    return build_suite(make_suite_dict())


@pytest.fixture
def tmp_repo_root(tmp_path: Path) -> Path:
    return tmp_path
