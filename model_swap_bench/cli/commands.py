"""CLI command implementations (thin Typer wrappers live in app.py)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.cli import output
from model_swap_bench.config import load_suite, schema_json
from model_swap_bench.config.models import BenchmarkSuite, ProviderKind
from model_swap_bench.errors import ConfigError, ExitCode, ProviderUnavailableError
from model_swap_bench.evaluators import registered_names
from model_swap_bench.execution import BenchmarkRunner
from model_swap_bench.pricing import WARNING, PricingRegistry
from model_swap_bench.providers.base import build_provider
from model_swap_bench.reports import RENDERERS
from model_swap_bench.reports.exit_report import (
    ExitReportThresholds,
    build_aimeter_export,
    build_audit_events,
    build_exit_report,
    render_aimeter_export_json,
    render_audit_events_jsonl,
    render_exit_report_json,
    render_exit_report_markdown,
)
from model_swap_bench.reports.route_plan import (
    RoutingThresholds,
    build_model_routing_plan,
    build_route_aimeter_export,
    build_route_audit_events,
    render_model_routing_plan_json,
    render_model_routing_plan_markdown,
    render_route_aimeter_export_json,
    render_route_audit_events_jsonl,
)
from model_swap_bench.results import BenchmarkRun, CaseStatus
from model_swap_bench.storage import RunRepository

# ---------------------------------------------------------------------------
# Inspection commands
# ---------------------------------------------------------------------------


def validate(file: Path) -> None:
    suite = load_suite(file)
    output.success(f"{file.name} is valid: {suite.name} v{suite.version}")
    output.info(f"  models: {len(suite.models)} | cases: {len(suite.cases)} | mode-hint: {suite.execution.mode or 'auto'}")


def print_schema(out: Path | None) -> None:
    text = schema_json()
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        output.success(f"schema written to {out}")
    else:
        output.info(text)


def list_models(file: Path) -> None:
    suite = load_suite(file)
    rows = [(m.alias, m.provider.value, m.model, m.deployment.value, "hosted" if m.is_hosted else "local") for m in suite.models]
    output.table(f"Models in {suite.name}", ["alias", "provider", "model", "deployment", "class"], rows)


def list_providers() -> None:
    rows = [(k.value, "hosted" if k.value in {"openai", "anthropic", "bedrock"} else "local/self-hosted") for k in ProviderKind]
    output.table("Providers", ["provider", "class"], rows)
    output.info("Evaluators: " + ", ".join(registered_names()))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _apply_overrides(
    suite: BenchmarkSuite,
    *,
    concurrency: int | None,
    timeout: float | None,
    repetitions: int | None,
    seed: int | None,
) -> None:
    if concurrency is not None:
        suite.execution.concurrency = concurrency
    if timeout is not None:
        suite.execution.timeout_seconds = timeout
    if repetitions is not None:
        suite.execution.repetitions = repetitions
    if seed is not None:
        suite.execution.seed = seed


def _dry_run(suite: BenchmarkSuite, suite_dir: Path, allow_hosted: bool) -> ExitCode:
    output.info(f"[bold]Dry run[/bold]: {suite.name} v{suite.version} — {len(suite.cases)} case(s)")
    unavailable = False
    for model in suite.models:
        try:
            provider = build_provider(model, suite_dir=suite_dir, allow_hosted=allow_hosted)
        except ProviderUnavailableError as exc:
            output.warn(f"{model.alias}: {exc}")
            unavailable = True
            continue
        health = asyncio.run(provider.health())
        asyncio.run(provider.aclose())
        (output.success if health.available else output.warn)(f"{model.alias}: {health.detail}")
        unavailable = unavailable or not (health.available or model.provider is ProviderKind.DETERMINISTIC)
    return ExitCode.PROVIDER_UNAVAILABLE if unavailable else ExitCode.SUCCESS


def run(
    file: Path,
    *,
    only_model: str | None = None,
    output_root: Path | None = None,
    concurrency: int | None = None,
    timeout: float | None = None,
    repetitions: int | None = None,
    seed: int | None = None,
    allow_hosted: bool = False,
    dry_run: bool = False,
) -> tuple[BenchmarkRun | None, ExitCode]:
    suite = load_suite(file)
    suite_dir = file.resolve().parent
    _apply_overrides(suite, concurrency=concurrency, timeout=timeout, repetitions=repetitions, seed=seed)

    if allow_hosted and not suite.privacy.allow_hosted_providers:
        output.warn("--allow-hosted set but suite privacy.allow_hosted_providers is false; hosted models stay disabled.")
    if any(m.is_hosted for m in suite.models) and (allow_hosted and suite.privacy.allow_hosted_providers):
        output.warn("Hosted providers enabled: benchmark inputs may leave this machine.")

    hosted_enabled = allow_hosted and suite.privacy.allow_hosted_providers

    if dry_run:
        return None, _dry_run(suite, suite_dir, hosted_enabled)

    only = {only_model} if only_model else None
    runner = BenchmarkRunner(suite, suite_dir=suite_dir, allow_hosted=hosted_enabled)
    run_result = asyncio.run(runner.run(only_models=only))

    repo = RunRepository(output_root or Path.cwd())
    repo.save(run_result, suite, suite_dir=suite_dir)
    _print_run_summary(run_result)
    return run_result, _run_exit_code(run_result)


def _run_exit_code(run_result: BenchmarkRun) -> ExitCode:
    if any(r.status is CaseStatus.ERROR for r in run_result.case_results):
        # Distinguish provider unavailability from ordinary constraint failure.
        if all(r.status is CaseStatus.ERROR for r in run_result.case_results):
            return ExitCode.PROVIDER_UNAVAILABLE
        return ExitCode.PARTIAL_RUN
    if not run_result.all_constraints_passed:
        return ExitCode.CONSTRAINTS_FAILED
    return ExitCode.SUCCESS


def _print_run_summary(run_result: BenchmarkRun) -> None:
    output.success(f"run {run_result.run_id} complete ({run_result.mode})")
    rows = [
        (
            s.model_alias,
            f"{s.success_rate * 100:.0f}%",
            f"{s.quality_score:.2f}",
            f"{s.p95_latency_ms:.0f}ms",
            "n/a" if s.cost_per_success_usd is None else f"${s.cost_per_success_usd:.6f}",
        )
        for s in run_result.model_summaries
    ]
    output.table("Summary", ["model", "success", "quality", "p95", "cost/success"], rows)
    for d in run_result.replacement_decisions:
        output.info(f"[bold]{d.candidate_model}[/bold] → {d.recommendation} (confidence {d.confidence:.0%})")
    if not run_result.all_constraints_passed:
        output.warn("one or more constraints FAILED (see `report`/`compare`)")


# ---------------------------------------------------------------------------
# Reporting / inspection of stored runs
# ---------------------------------------------------------------------------


def report(run_ref: str, *, fmt: str, out: Path | None, root: Path | None) -> None:
    repo = RunRepository(root or Path.cwd())
    run_result = repo.load(run_ref)
    renderer = RENDERERS.get(fmt)
    if renderer is None:
        from model_swap_bench.errors import ConfigError

        raise ConfigError(f"unknown format {fmt!r}; choose from {', '.join(RENDERERS)}")
    text = renderer(run_result)
    if out:
        out.write_text(text, encoding="utf-8")
        output.success(f"{fmt} report written to {out}")
    else:
        output.info(text)


def exit_report(
    *,
    baseline: str,
    candidate: str,
    input_file: Path,
    output_file: Path,
    fmt: str,
    title: str,
    workload: str | None,
    risk_profile: str,
    min_quality_retention: float,
    max_latency_increase: float,
    min_cost_reduction: float,
    export_aimeter: Path | None,
    export_auditlog: Path | None,
    run_id: str | None,
    system_id: str,
    actor: str,
    audit_hash_chain: bool,
) -> None:
    if fmt not in {"markdown", "json"}:
        raise ConfigError("unknown exit-report format; choose markdown or json")
    thresholds = ExitReportThresholds(
        min_quality_retention_pct=Decimal(str(min_quality_retention)),
        max_latency_increase_pct=Decimal(str(max_latency_increase)),
        min_cost_reduction_pct=Decimal(str(min_cost_reduction)),
    )
    command = (
        "modelswapbench exit-report "
        f"--baseline {baseline} --candidate {candidate} --input {input_file} --output {output_file} --format {fmt}"
    )
    if export_aimeter:
        command += f" --export-aimeter {export_aimeter}"
    if export_auditlog:
        command += f" --export-auditlog {export_auditlog}"
    report_payload = build_exit_report(
        input_path=input_file,
        baseline_ref=baseline,
        candidate_ref=candidate,
        title=title,
        workload=workload,
        risk_profile=risk_profile,
        thresholds=thresholds,
        cli_command=command,
    )
    text = render_exit_report_markdown(report_payload) if fmt == "markdown" else render_exit_report_json(report_payload)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(text, encoding="utf-8")
    output.success(f"exit report written to {output_file}")
    if export_aimeter:
        aimeter_export = build_aimeter_export(report_payload)
        export_aimeter.parent.mkdir(parents=True, exist_ok=True)
        export_aimeter.write_text(render_aimeter_export_json(aimeter_export), encoding="utf-8")
        output.success(f"AIMeter OSS-style export written to {export_aimeter}")
    if export_auditlog:
        audit_events = build_audit_events(
            report_payload,
            run_id=run_id,
            system_id=system_id,
            actor=actor,
            hash_chain=audit_hash_chain,
            include_aimeter_export_event=export_aimeter is not None,
        )
        export_auditlog.parent.mkdir(parents=True, exist_ok=True)
        export_auditlog.write_text(render_audit_events_jsonl(audit_events), encoding="utf-8")
        output.success(f"AIAuditLog-style audit events written to {export_auditlog}")
    output.info(f"Decision: {report_payload.decision.decision.value}")


def route_plan(
    *,
    input_file: Path,
    output_file: Path,
    fmt: str,
    baseline: str,
    candidate: str,
    workload: str | None,
    risk_profile: str,
    min_quality_retention: float,
    max_latency_increase: float,
    min_cost_reduction: float,
    export_json: Path | None,
    export_aimeter: Path | None,
    export_auditlog: Path | None,
    run_id: str | None,
    system_id: str,
    actor: str,
    audit_hash_chain: bool,
) -> None:
    if fmt not in {"markdown", "json"}:
        raise ConfigError("unknown route-plan format; choose markdown or json")
    destinations = {
        "output": output_file,
        "JSON export": export_json,
        "AIMeter export": export_aimeter,
        "audit-log export": export_auditlog,
    }
    input_path = input_file.resolve(strict=False)
    seen_destinations: dict[Path, str] = {}
    destination_paths: list[tuple[Path, str]] = []
    for label, destination in destinations.items():
        if destination is None:
            continue
        resolved = destination.resolve(strict=False)
        same_as_input = resolved == input_path or (input_file.exists() and destination.exists() and destination.samefile(input_file))
        if same_as_input:
            raise ConfigError(f"{label} path must not overwrite the route-plan input")
        collision = seen_destinations.get(resolved)
        if collision is None:
            collision = next(
                (
                    previous_label
                    for previous_path, previous_label in destination_paths
                    if destination.exists() and previous_path.exists() and destination.samefile(previous_path)
                ),
                None,
            )
        if collision is not None:
            raise ConfigError(f"{label} path collides with {collision} path")
        seen_destinations[resolved] = label
        destination_paths.append((destination, label))
    try:
        thresholds = RoutingThresholds(
            min_quality_retention_pct=Decimal(str(min_quality_retention)),
            max_latency_increase_pct=Decimal(str(max_latency_increase)),
            min_cost_reduction_pct=Decimal(str(min_cost_reduction)),
        )
    except PydanticValidationError as exc:
        raise ConfigError("route-plan thresholds must be finite, non-negative percentages") from exc
    command = f"modelswapbench route-plan --input {input_file} --output {output_file} --format {fmt}"
    if export_json:
        command += f" --export-json {export_json}"
    if export_aimeter:
        command += f" --export-aimeter {export_aimeter}"
    if export_auditlog:
        command += f" --export-auditlog {export_auditlog}"
    plan = build_model_routing_plan(
        input_path=input_file,
        baseline_model=baseline,
        candidate_model=candidate,
        workload=workload,
        risk_profile=risk_profile,
        thresholds=thresholds,
        run_id=run_id,
        cli_command=command,
    )
    text = render_model_routing_plan_markdown(plan) if fmt == "markdown" else render_model_routing_plan_json(plan)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(text, encoding="utf-8")
    output.success(f"route plan written to {output_file}")
    if export_json:
        export_json.parent.mkdir(parents=True, exist_ok=True)
        export_json.write_text(render_model_routing_plan_json(plan), encoding="utf-8")
        output.success(f"route plan JSON written to {export_json}")
    if export_aimeter:
        aimeter_export = build_route_aimeter_export(plan)
        export_aimeter.parent.mkdir(parents=True, exist_ok=True)
        export_aimeter.write_text(render_route_aimeter_export_json(aimeter_export), encoding="utf-8")
        output.success(f"AIMeter OSS-style route export written to {export_aimeter}")
    if export_auditlog:
        audit_events = build_route_audit_events(
            plan,
            system_id=system_id,
            actor=actor,
            hash_chain=audit_hash_chain,
            include_aimeter_export_event=export_aimeter is not None,
        )
        export_auditlog.parent.mkdir(parents=True, exist_ok=True)
        export_auditlog.write_text(render_route_audit_events_jsonl(audit_events), encoding="utf-8")
        output.success(f"AIAuditLog-style route audit events written to {export_auditlog}")
    output.info(f"Candidate route share: {plan.summary.candidate_model_pct.quantize(Decimal('0.01'))}%")


def compare(run_ref: str, *, root: Path | None) -> ExitCode:
    repo = RunRepository(root or Path.cwd())
    run_result = repo.load(run_ref)
    rows = [
        (
            s.model_alias,
            f"{s.success_rate * 100:.0f}%",
            f"{s.quality_score:.2f}",
            f"{s.valid_json_rate * 100:.0f}%",
            f"{s.p95_latency_ms:.0f}ms",
            "n/a" if s.cost_per_success_usd is None else f"${s.cost_per_success_usd:.6f}",
        )
        for s in run_result.model_summaries
    ]
    output.table(f"Comparison — {run_result.suite_name}", ["model", "success", "quality", "json", "p95", "cost/succ"], rows)
    for d in run_result.replacement_decisions:
        output.info("")
        output.info(f"[bold]{d.candidate_model} vs {d.baseline_model}[/bold]: {d.recommendation} (confidence {d.confidence:.0%})")
        for e in d.evidence:
            output.info(f"  - {e}")
        for f in d.failed_constraints:
            output.warn(f"  failed: {f}")
    if run_result.cascade_summary is not None:
        cs = run_result.cascade_summary
        output.info("")
        output.info(f"[bold]Cascade[/bold]: {cs.final_success_rate * 100:.0f}% final success, {cs.escalation_rate * 100:.0f}% escalated")
    return ExitCode.SUCCESS if run_result.all_constraints_passed else ExitCode.CONSTRAINTS_FAILED


def runs_list(root: Path | None) -> None:
    repo = RunRepository(root or Path.cwd())
    runs = repo.list_runs()
    if not runs:
        output.warn("no runs found")
        return
    rows = [(r["run_id"], r["suite_name"], r["mode"], r["created_at"], "pass" if r["constraints_passed"] else "FAIL") for r in runs]
    output.table("Runs", ["run_id", "suite", "mode", "created", "constraints"], rows)


def runs_show(run_ref: str, root: Path | None) -> None:
    repo = RunRepository(root or Path.cwd())
    run_result = repo.load(run_ref)
    manifest = repo.load_manifest(run_ref)
    output.info(f"[bold]{run_result.run_id}[/bold] — {run_result.suite_name} v{run_result.suite_version} ({run_result.mode})")
    output.info(f"  manifest hash: {run_result.manifest_hash[:16]} | cases: {len(run_result.case_results)}")
    output.info(
        f"  package: {manifest.get('package_version')} | forge: {manifest.get('forge_version')} | python: {manifest.get('python_version')}"
    )
    output.info(f"  git commit: {manifest.get('git_commit') or 'n/a'}")


def reproduce(run_ref: str, root: Path | None) -> tuple[BenchmarkRun, ExitCode]:
    repo = RunRepository(root or Path.cwd())
    run_id = repo.resolve(run_ref)
    old_manifest = repo.load_manifest(run_ref)
    suite = repo.load_suite_snapshot(run_id)
    suite_dir = repo.run_dir(run_id)
    runner = BenchmarkRunner(suite, suite_dir=suite_dir)
    new_run = asyncio.run(runner.run())
    from model_swap_bench.storage.manifests import build_manifest

    fresh = build_manifest(suite, new_run.run_id, suite_dir)
    _warn_drift(old_manifest, fresh)
    repo.save(new_run, suite, suite_dir=suite_dir)
    output.success(f"reproduced as {new_run.run_id}")
    _print_run_summary(new_run)
    return new_run, _run_exit_code(new_run)


def _warn_drift(old: dict[str, object], new: dict[str, object]) -> None:
    for key in ("package_version", "forge_version", "python_version"):
        if old.get(key) != new.get(key):
            output.warn(f"version drift: {key} was {old.get(key)!r}, now {new.get(key)!r} — results may differ")
    if old.get("suite_hash") != new.get("suite_hash"):
        output.warn("suite definition changed since the original run")


def clean(run_ref: str, root: Path | None) -> None:
    repo = RunRepository(root or Path.cwd())
    deleted = repo.delete(run_ref)
    output.success(f"deleted run {deleted}")


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def pricing_show(path: Path | None) -> None:
    registry = PricingRegistry.load(path)
    output.warn(WARNING)
    rows = [
        (e.model, e.provider, f"{e.input_price}", f"{e.output_price}", "measured" if e.measured else "estimate") for e in registry.entries
    ]
    output.table(f"Pricing (v{registry.version})", ["model", "provider", "in/Mtok", "out/Mtok", "kind"], rows)


def pricing_validate(path: Path | None) -> ExitCode:
    registry = PricingRegistry.load(path)
    problems = registry.validate_entries()
    if problems:
        for p in problems:
            output.error(p)
        return ExitCode.INVALID_INPUT
    output.success(f"pricing registry valid ({len(registry.entries)} entries)")
    return ExitCode.SUCCESS


def pricing_set(model: str, provider: str, input_price: float, output_price: float, path: Path) -> None:
    registry = PricingRegistry.load(path) if path.exists() else PricingRegistry()
    registry.set_price(model, provider, input_price, output_price, source="set via CLI")
    registry.save(path)
    output.success(f"set {model} ({provider}) to in={input_price} out={output_price} in {path}")
    output.warn(WARNING)


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------

EXAMPLES = [
    ("support-ticket-triage", "Classify support tickets; JSON schema + field match + policy (offline)."),
    ("local-rag-citations", "Grounded answers with citation checking (offline fixtures / local Ollama)."),
    ("code-review-summary", "Structured severity + required remediation; forbids 'fully secure' claims."),
    ("cascade-routing", "Cheap local model first, escalate failures to a stronger fixture model."),
    ("vendor_exit", "AI Vendor Exit Report input and sample Markdown output."),
    ("route_plan", "Model Routing Plan input and sample Markdown/JSON outputs."),
]


def examples_list() -> None:
    rows = [(name, desc) for name, desc in EXAMPLES]
    output.table("Bundled examples (examples/<name>/benchmark.yaml)", ["example", "description"], rows)
