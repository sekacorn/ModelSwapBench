"""Self-contained HTML report.

Renders the Markdown report inside a minimal, dependency-free HTML shell. All
dynamic content is HTML-escaped to avoid injection from model output.
"""

from __future__ import annotations

import html

from model_swap_bench.reports.markdown import render_markdown
from model_swap_bench.results import BenchmarkRun

_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; max-width: 60rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
pre { background: #f5f5f5; padding: 1rem; overflow-x: auto; border-radius: 6px; }
code { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; }
"""


def render_html(run: BenchmarkRun) -> str:
    """Render a minimal, self-contained HTML report (Markdown source shown as text)."""
    markdown_source = render_markdown(run)
    body = html.escape(markdown_source)
    title = html.escape(f"ModelSwapBench — {run.suite_name}")
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title}</title>\n<style>{_STYLE}</style>\n</head>\n<body>\n"
        f"<h1>{title}</h1>\n<pre>{body}</pre>\n</body>\n</html>\n"
    )
