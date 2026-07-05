"""CSV summary — one row per model, for spreadsheets and procurement."""

from __future__ import annotations

import csv
import io

from model_swap_bench.results import BenchmarkRun

_COLUMNS = [
    "model_alias",
    "provider",
    "deployment",
    "total_cases",
    "successful_cases",
    "success_rate",
    "quality_score",
    "valid_json_rate",
    "policy_pass_rate",
    "tool_accuracy",
    "avg_latency_ms",
    "p95_latency_ms",
    "total_cost_usd",
    "cost_per_success_usd",
    "timeout_rate",
    "escalation_rate",
]


def render_csv(run: BenchmarkRun) -> str:
    """Render the per-model summary table as CSV."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for summary in run.model_summaries:
        row = summary.model_dump()
        writer.writerow({k: row.get(k) for k in _COLUMNS})
    return buffer.getvalue()
