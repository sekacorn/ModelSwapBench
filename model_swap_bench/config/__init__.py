"""Benchmark configuration: typed models, loading, validation, and JSON Schema."""

from __future__ import annotations

from model_swap_bench.config.loader import build_suite, load_mapping, load_suite
from model_swap_bench.config.models import (
    BenchmarkCase,
    BenchmarkSuite,
    CascadeCondition,
    CascadeConfig,
    Constraints,
    CostMode,
    DeploymentType,
    EvaluatorSpec,
    ExecutionConfig,
    ExecutionMode,
    ModelCandidate,
    PolicyExpectation,
    PrivacyConfig,
    ProviderKind,
    ReplacementConfig,
    ScoringConfig,
)
from model_swap_bench.config.schema import benchmark_json_schema, schema_json
from model_swap_bench.config.validation import validate_suite

__all__ = [
    "BenchmarkCase",
    "BenchmarkSuite",
    "CascadeCondition",
    "CascadeConfig",
    "Constraints",
    "CostMode",
    "DeploymentType",
    "EvaluatorSpec",
    "ExecutionConfig",
    "ExecutionMode",
    "ModelCandidate",
    "PolicyExpectation",
    "PrivacyConfig",
    "ProviderKind",
    "ReplacementConfig",
    "ScoringConfig",
    "benchmark_json_schema",
    "build_suite",
    "load_mapping",
    "load_suite",
    "schema_json",
    "validate_suite",
]
