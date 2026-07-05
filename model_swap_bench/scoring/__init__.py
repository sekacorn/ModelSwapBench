"""Scoring: metrics, economics, aggregation, and the replacement decision engine."""

from __future__ import annotations

from model_swap_bench.scoring.aggregation import build_model_summary, check_constraints
from model_swap_bench.scoring.economics import cost_per_success, estimate_call_cost
from model_swap_bench.scoring.replacement import decide_replacement

__all__ = [
    "build_model_summary",
    "check_constraints",
    "cost_per_success",
    "decide_replacement",
    "estimate_call_cost",
]
