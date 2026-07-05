"""JSON report — the full, machine-readable run record."""

from __future__ import annotations

import json

from model_swap_bench.results import BenchmarkRun


def render_json(run: BenchmarkRun, *, indent: int = 2) -> str:
    """Serialize a complete run to indented JSON."""
    return json.dumps(run.model_dump(mode="json"), indent=indent, default=str)
