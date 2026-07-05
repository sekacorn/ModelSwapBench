"""Report renderers: Markdown, JSON, CSV, and self-contained HTML."""

from __future__ import annotations

from collections.abc import Callable

from model_swap_bench.reports.csv_report import render_csv
from model_swap_bench.reports.html import render_html
from model_swap_bench.reports.json_report import render_json
from model_swap_bench.reports.markdown import render_markdown
from model_swap_bench.results import BenchmarkRun

#: Report format name -> renderer.
RENDERERS: dict[str, Callable[[BenchmarkRun], str]] = {
    "markdown": render_markdown,
    "json": render_json,
    "csv": render_csv,
    "html": render_html,
}

__all__ = ["RENDERERS", "render_csv", "render_html", "render_json", "render_markdown"]
