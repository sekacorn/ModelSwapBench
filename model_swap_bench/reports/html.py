"""Readable, dependency-free static HTML decision report."""

from __future__ import annotations

import html

from model_swap_bench.results import BenchmarkRun

_STYLE = """
:root { color-scheme: light; font-family: Segoe UI, Arial, sans-serif; color: #17202a; background: #f4f6f7; }
body { max-width: 72rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
h1, h2 { letter-spacing: 0; } h1 { font-size: 2rem; margin-bottom: .25rem; } h2 { margin-top: 2rem; }
.lede { color: #566573; margin-top: 0; } .status { border-left: .35rem solid #2471a3; padding: .75rem 1rem; background: #fff; }
table { width: 100%; border-collapse: collapse; background: #fff; } th, td { padding: .65rem; border: 1px solid #d5d8dc; text-align: left; }
th { background: #eaecee; } .unknown { color: #7d6608; } .warning { color: #922b21; } code { overflow-wrap: anywhere; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1rem; } dt { font-weight: 600; } dd { margin: 0; }
@media (max-width: 48rem) { body { padding: 1rem .5rem; } table { display: block; overflow-x: auto; } dl { grid-template-columns: 1fr; } }
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _pct(value: float | None) -> str:
    return "Unknown" if value is None else f"{value * 100:.1f}%"


def _cost(value: float | None) -> str:
    return "Unknown" if value is None else f"${value:.6f} estimated"


def render_html(run: BenchmarkRun) -> str:
    """Render a deterministic static decision report with escaped content."""
    title = f"ModelSwapBench decision report: {run.suite_name}"
    decisions = (
        "".join(
            "<tr>"
            f"<td>{_e(item.candidate_model)}</td><td>{_e(item.baseline_model)}</td>"
            f"<td>{_e(item.recommendation)}</td><td>{item.confidence:.0%}</td>"
            f"<td>{_e('; '.join(item.risks) or 'None recorded')}</td>"
            "</tr>"
            for item in run.replacement_decisions
        )
        or '<tr><td colspan="5" class="unknown">No replacement decision was produced.</td></tr>'
    )
    summaries = (
        "".join(
            "<tr>"
            f"<td>{_e(item.model_alias)}</td><td>{item.total_cases}</td><td>{_pct(item.success_rate)}</td>"
            f"<td>{item.quality_score:.3f}</td><td>{_pct(item.policy_pass_rate)}</td>"
            f"<td>{item.median_latency_ms:.1f}</td><td>{item.p90_latency_ms:.1f}</td><td>{item.p95_latency_ms:.1f}</td>"
            f"<td>{_cost(item.total_cost_usd)}</td><td>{_cost(item.cost_per_success_usd)}</td>"
            "</tr>"
            for item in run.model_summaries
        )
        or '<tr><td colspan="10" class="unknown">No model summaries were produced.</td></tr>'
    )
    warnings = "".join(f"<li>{_e(item)}</li>" for item in run.warnings) or "<li>None recorded.</li>"
    recommendation = run.replacement_decisions[0].recommendation if run.replacement_decisions else "Insufficient evidence"
    constraints = "passed" if run.all_constraints_passed else "failed"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            f"<title>{_e(title)}</title><style>{_STYLE}</style></head><body>",
            f'<header><h1>{_e(title)}</h1><p class="lede">Evidence for task routing and model replacement, '
            "not a universal model ranking.</p></header>",
            f'<section class="status"><strong>Executive recommendation:</strong> {_e(recommendation)}. '
            f"Constraints: {constraints}.</section>",
            "<h2>Replacement decisions</h2><table><thead><tr><th>Candidate</th><th>Baseline</th>"
            f"<th>Recommendation</th><th>Confidence</th><th>Risks</th></tr></thead><tbody>{decisions}</tbody></table>",
            "<h2>Evidence summary</h2><table><thead><tr><th>Model</th><th>Samples</th><th>Success</th>"
            "<th>Quality</th><th>Policy</th><th>Median ms</th><th>p90 ms</th><th>p95 ms</th>"
            f"<th>Total cost</th><th>Cost/success</th></tr></thead><tbody>{summaries}</tbody></table>",
            f"<h2>Unknowns and warnings</h2><ul>{warnings}</ul>",
            f"<h2>Reproducibility</h2><dl><dt>Run ID</dt><dd><code>{_e(run.run_id)}</code></dd>"
            f"<dt>Suite version</dt><dd>{_e(run.suite_version)}</dd><dt>Mode</dt><dd>{_e(run.mode)}</dd>"
            f"<dt>Dataset/run digest</dt><dd><code>{_e(run.manifest_hash or 'Unknown')}</code></dd>"
            f"<dt>Created</dt><dd>{_e(run.created_at.isoformat())}</dd></dl>",
            "<h2>Limitations</h2><ul><li>Small or unrepresentative datasets can produce misleading recommendations.</li>"
            "<li>Missing signals remain unknown and should trigger review.</li>"
            "<li>Costs are estimates from operator-supplied assumptions, not invoice-confirmed spend.</li>"
            "<li>Projected savings are not realized savings.</li></ul>",
            "</body></html>",
            "",
        ]
    )
