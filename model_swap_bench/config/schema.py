"""JSON Schema generation for the benchmark format.

The schema is derived directly from the Pydantic models so it can never drift
from the actual validation logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model_swap_bench.config.models import BenchmarkSuite

_RESOURCE = Path(__file__).resolve().parent.parent / "resources" / "benchmark.schema.json"


def benchmark_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a :class:`BenchmarkSuite`."""
    schema = BenchmarkSuite.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "ModelSwapBench Benchmark Suite"
    return schema


def schema_json(indent: int = 2) -> str:
    """Return the benchmark JSON Schema as a formatted string."""
    return json.dumps(benchmark_json_schema(), indent=indent, sort_keys=False)


def write_schema_resource() -> Path:
    """Write the schema to the packaged resource path and return it."""
    _RESOURCE.parent.mkdir(parents=True, exist_ok=True)
    _RESOURCE.write_text(schema_json() + "\n", encoding="utf-8")
    return _RESOURCE
