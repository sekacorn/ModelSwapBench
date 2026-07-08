"""Human-readable Markdown report.

Shows *why* each candidate passed or failed — never a single composite score in
isolation. Failures, timeouts, and limitations are always surfaced.
"""

from __future__ import annotations

from model_swap_bench.config.models import BenchmarkSuite
from model_swap_bench.results import BenchmarkRun, CaseResult, CaseStatus, EvalStatus, ModelSummary

_LIMITATIONS = [
    "Results are evidence for a replacement decision, not proof that one model is universally better.",
    "Cost figures are estimates from a user-editable registry / compute profile — not measured billing.",
    "Deterministic providers simulate behavior; only Ollama / OpenAI-compatible runs reflect real models.",
    "Small case counts yield low-confidence decisions; add cases and repetitions before committing.",
]


def _fmt_cost(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.6f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _summary_row(s: ModelSummary) -> str:
    tool = "n/a" if s.tool_accuracy is None else _fmt_pct(s.tool_accuracy)
    return (
        f"| {s.model_alias} | {s.provider}/{s.deployment} | {_fmt_pct(s.success_rate)} | {s.quality_score:.2f} "
        f"| {_fmt_pct(s.valid_json_rate)} | {_fmt_pct(s.policy_pass_rate)} | {tool} | {s.p95_latency_ms:.0f} "
        f"| {_fmt_cost(s.total_cost_usd)} | {_fmt_cost(s.cost_per_success_usd)} |"
    )


def _case_line(r: CaseResult) -> str:
    marks = []
    for e in r.evaluations:
        if e.status is EvalStatus.SKIPPED:
            symbol = "-"
        elif e.passed:
            symbol = "✓"
        else:
            symbol = "✗"
        marks.append(f"{e.evaluator}:{symbol}")
    return f"| {r.case_id} | {r.status.value} | {r.latency_ms:.0f}ms | {_fmt_cost(r.estimated_cost_usd)} | {', '.join(marks)} |"


def render_markdown(run: BenchmarkRun, *, suite: BenchmarkSuite | None = None) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"# ModelSwapBench Report — {run.suite_name}")
    add("")
    add(f"- Run ID: `{run.run_id}`")
    add(f"- Suite version: {run.suite_version}")
    add(f"- Mode: {run.mode}")
    add(f"- Baseline: {run.baseline_model or 'n/a'}")
    add(f"- Manifest hash: `{run.manifest_hash[:16]}`")
    add(f"- Created: {run.created_at.isoformat()}")
    add("")

    # Executive summary
    add("## Executive summary")
    add("")
    if run.replacement_decisions:
        for d in run.replacement_decisions:
            add(f"- **{d.candidate_model}** vs {d.baseline_model}: **{d.recommendation}** (confidence {d.confidence:.0%}).")
    else:
        best = max(run.model_summaries, key=lambda s: (s.success_rate, s.quality_score), default=None)
        if best is not None:
            add(f"- Best success rate: **{best.model_alias}** at {_fmt_pct(best.success_rate)}.")
    add(f"- Constraints: {'all passed' if run.all_constraints_passed else 'one or more FAILED'}.")
    add("")

    # Model comparison
    add("## Model comparison")
    add("")
    add("| Model | Provider | Success | Quality | Valid JSON | Policy | Tools | p95 ms | Total cost | Cost/success |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for s in run.model_summaries:
        add(_summary_row(s))
    add("")

    # Constraints
    add("## Constraints")
    add("")
    for alias, checks in run.constraint_results.items():
        if not checks:
            continue
        add(f"**{alias}**")
        add("")
        add("| Constraint | Threshold | Actual | Result |")
        add("|---|---|---|---|")
        for c in checks:
            add(f"| {c.name} | {c.threshold} | {c.actual} | {'PASS' if c.passed else 'FAIL'} |")
        add("")

    # Replacement decisions
    if run.replacement_decisions:
        add("## Replacement recommendations")
        add("")
        for d in run.replacement_decisions:
            add(f"### {d.candidate_model} → replace {d.baseline_model}?")
            add("")
            add(f"**Decision: {d.recommendation}** (confidence {d.confidence:.0%}, eligible={d.eligible})")
            add("")
            add("Evidence:")
            for e in d.evidence:
                add(f"- {e}")
            if d.failed_constraints:
                add("")
                add("Failed constraints:")
                for f in d.failed_constraints:
                    add(f"- {f}")
            if d.risks:
                add("")
                add("Risks:")
                for r in d.risks:
                    add(f"- {r}")
            add("")
            add(f"Recommended next step: {d.recommended_next_step}")
            add("")

    # Cascade
    if run.cascade_summary is not None:
        cs = run.cascade_summary
        add("## Cascade analysis")
        add("")
        add(f"- First stage: {cs.first_stage_model} ({_fmt_pct(cs.first_stage_success_rate)} direct success)")
        add(f"- Escalation model: {cs.escalation_model}")
        add(f"- Escalation rate: {_fmt_pct(cs.escalation_rate)}")
        add(f"- Final success rate: {_fmt_pct(cs.final_success_rate)}")
        add(f"- Combined cost: {_fmt_cost(cs.total_cost_usd)} (cost/success {_fmt_cost(cs.cost_per_success_usd)})")
        add("")

    # Per-case
    add("## Per-case results")
    add("")
    by_model: dict[str, list[CaseResult]] = {}
    for res in run.case_results:
        by_model.setdefault(res.model_alias, []).append(res)
    for alias, results in by_model.items():
        add(f"### {alias}")
        add("")
        add("| Case | Status | Latency | Cost | Evaluators |")
        add("|---|---|---|---|---|")
        for res in results:
            add(_case_line(res))
        add("")

    # Failures / timeouts
    failures = [res for res in run.case_results if res.status in (CaseStatus.FAILED, CaseStatus.ERROR, CaseStatus.TIMEOUT)]
    if failures:
        add("## Failures, errors, and timeouts")
        add("")
        for res in failures:
            detail = res.error or "; ".join(e.explanation for e in res.evaluations if not e.passed and e.status is not EvalStatus.SKIPPED)
            add(f"- `{res.model_alias}` / `{res.case_id}` — {res.status.value}: {detail[:200]}")
        add("")

    # Privacy / deployment
    add("## Privacy & deployment classification")
    add("")
    for s in run.model_summaries:
        add(f"- {s.model_alias}: provider `{s.provider}`, deployment `{s.deployment}`")
    if suite is not None:
        add(f"- Hosted providers allowed: {suite.privacy.allow_hosted_providers}")
    add("")

    if run.warnings:
        add("## Warnings")
        add("")
        for w in run.warnings:
            add(f"- {w}")
        add("")

    add("## Known limitations")
    add("")
    for lim in _LIMITATIONS:
        add(f"- {lim}")
    add("")
    add("> Pricing values are user-configurable estimates and may become outdated.")
    add("")
    return "\n".join(lines)
