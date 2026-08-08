"""Typer CLI entry point for ``modelswapbench``.

Exit codes (stable contract): 0 success, 1 constraints failed, 2 invalid input,
3 provider unavailable, 4 partial run, 5 internal error.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from model_swap_bench._version import __version__
from model_swap_bench.cli import commands, doctor, output
from model_swap_bench.cli.doctor import FAIL, PASS, WARN
from model_swap_bench.errors import ExitCode, ModelSwapBenchError

app = typer.Typer(
    name="modelswapbench",
    help="Open-source model portability and replacement benchmark.",
    no_args_is_help=True,
    add_completion=False,
)
runs_app = typer.Typer(help="Inspect stored runs.", no_args_is_help=True)
pricing_app = typer.Typer(help="Manage the pricing registry.", no_args_is_help=True)
examples_app = typer.Typer(help="Bundled examples.", no_args_is_help=True)
dataset_app = typer.Typer(help="Manage private local evaluation datasets.", no_args_is_help=True)
outcomes_app = typer.Typer(help="Import and summarize human outcome labels.", no_args_is_help=True)
workflow_app = typer.Typer(help="Evaluate multi-turn and tool workflow traces.", no_args_is_help=True)
replay_app = typer.Typer(help="Sanitize local production trace replays.", no_args_is_help=True)
telemetry_app = typer.Typer(help="Export portable OpenTelemetry-compatible records.", no_args_is_help=True)
app.add_typer(runs_app, name="runs")
app.add_typer(pricing_app, name="pricing")
app.add_typer(examples_app, name="examples")
app.add_typer(dataset_app, name="dataset")
app.add_typer(outcomes_app, name="outcomes")
app.add_typer(workflow_app, name="workflow")
app.add_typer(replay_app, name="replay")
app.add_typer(telemetry_app, name="telemetry")

VERBOSE = {"on": False}


def guard(func: Callable[..., Any]) -> Callable[..., Any]:
    """Translate ModelSwapBenchError into a clean message + stable exit code."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ModelSwapBenchError as exc:
            output.error(str(exc))
            raise typer.Exit(code=int(exc.exit_code)) from exc
        except typer.Exit:
            raise
        except Exception as exc:  # noqa: BLE001 - top-level safety net
            if VERBOSE["on"]:
                raise
            output.error(f"internal error: {exc}")
            raise typer.Exit(code=int(ExitCode.INTERNAL_ERROR)) from exc

    return wrapper


def _version_callback(value: bool) -> None:
    if value:
        output.info(f"modelswapbench {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[bool, typer.Option("--version", callback=_version_callback, is_eager=True)] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Show full tracebacks.")] = False,
) -> None:
    VERBOSE["on"] = verbose


@app.command("doctor")
@guard
def doctor_cmd() -> None:
    """Diagnose the environment (read-only)."""
    checks = doctor.run_checks()
    style = {PASS: output.success, WARN: output.warn, FAIL: output.error}
    for check in checks:
        printer = style.get(check.status, output.info)
        suffix = f" — fix: {check.fix}" if check.fix else ""
        printer(f"[{check.status}] {check.name}: {check.detail}{suffix}")
    if any(c.status == FAIL for c in checks):
        raise typer.Exit(code=int(ExitCode.INTERNAL_ERROR))


@app.command()
@guard
def validate(file: Annotated[Path, typer.Argument(help="Benchmark YAML/JSON file.")]) -> None:
    """Validate a benchmark file."""
    commands.validate(file)


@app.command()
@guard
def schema(output_file: Annotated[Path | None, typer.Option("--output", help="Write schema here.")] = None) -> None:
    """Print or export the benchmark JSON Schema."""
    commands.print_schema(output_file)


@app.command()
@guard
def models(file: Annotated[Path, typer.Argument(help="Benchmark file.")]) -> None:
    """List the models defined in a benchmark file."""
    commands.list_models(file)


@app.command()
@guard
def providers() -> None:
    """List supported providers and evaluators."""
    commands.list_providers()


@app.command()
@guard
def run(
    file: Annotated[Path, typer.Argument(help="Benchmark file.")],
    model: Annotated[str | None, typer.Option("--model", help="Run only this model alias.")] = None,
    output_dir: Annotated[Path | None, typer.Option("--output", help="Storage root (default: cwd).")] = None,
    concurrency: Annotated[int | None, typer.Option("--concurrency")] = None,
    timeout: Annotated[float | None, typer.Option("--timeout")] = None,
    repetitions: Annotated[int | None, typer.Option("--repetitions")] = None,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    allow_hosted: Annotated[bool, typer.Option("--allow-hosted", help="Permit hosted providers (data may leave the machine).")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate + health-check without executing.")] = False,
) -> None:
    """Run a benchmark suite."""
    _run, code = commands.run(
        file,
        only_model=model,
        output_root=output_dir,
        concurrency=concurrency,
        timeout=timeout,
        repetitions=repetitions,
        seed=seed,
        allow_hosted=allow_hosted,
        dry_run=dry_run,
    )
    if code is not ExitCode.SUCCESS:
        raise typer.Exit(code=int(code))


@app.command()
@guard
def compare(
    run_id: Annotated[str, typer.Argument(help="Run id or 'latest'.")] = "latest",
    output_dir: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Compare models in a stored run."""
    code = commands.compare(run_id, root=output_dir)
    if code is not ExitCode.SUCCESS:
        raise typer.Exit(code=int(code))


@app.command()
@guard
def report(
    run_id: Annotated[str, typer.Argument(help="Run id or 'latest'.")] = "latest",
    fmt: Annotated[str, typer.Option("--format", help="markdown|json|csv|html")] = "markdown",
    output_file: Annotated[Path | None, typer.Option("--output")] = None,
    output_dir: Annotated[Path | None, typer.Option("--root", help="Storage root.")] = None,
) -> None:
    """Render a report for a stored run."""
    commands.report(run_id, fmt=fmt, out=output_file, root=output_dir)


@app.command("exit-report")
@guard
def exit_report(
    baseline: Annotated[str, typer.Option("--baseline", help="Baseline provider:model, model, or label.")],
    candidate: Annotated[str, typer.Option("--candidate", help="Candidate provider:model, model, or label.")],
    input_file: Annotated[Path, typer.Option("--input", help="Benchmark summary JSON or JSONL fixture.")],
    output_file: Annotated[Path, typer.Option("--output", help="Report output path.")],
    fmt: Annotated[str, typer.Option("--format", help="markdown|json")] = "markdown",
    title: Annotated[str, typer.Option("--title", help="Report title.")] = "AI Vendor Exit Report",
    workload: Annotated[str | None, typer.Option("--workload", help="Workload label.")] = None,
    risk_profile: Annotated[str, typer.Option("--risk-profile", help="low|medium|high|regulated")] = "medium",
    min_quality_retention: Annotated[
        float, typer.Option("--min-quality-retention", help="Minimum acceptable quality retention percentage.")
    ] = 80.0,
    max_latency_increase: Annotated[
        float, typer.Option("--max-latency-increase", help="Maximum acceptable latency increase percentage.")
    ] = 50.0,
    min_cost_reduction: Annotated[float, typer.Option("--min-cost-reduction", help="Minimum expected cost reduction percentage.")] = 20.0,
    export_aimeter: Annotated[
        Path | None,
        typer.Option("--export-aimeter", help="Write an AIMeter OSS-style cost/outcome summary JSON file."),
    ] = None,
    export_auditlog: Annotated[
        Path | None,
        typer.Option("--export-auditlog", help="Write AIAuditLog-style audit events as JSONL."),
    ] = None,
    run_id: Annotated[str | None, typer.Option("--run-id", help="Run identifier for portable exports.")] = None,
    system_id: Annotated[str, typer.Option("--system-id", help="System identifier for audit events.")] = "modelswapbench",
    actor: Annotated[str, typer.Option("--actor", help="Actor identifier for audit events.")] = "modelswapbench-cli",
    audit_hash_chain: Annotated[
        bool,
        typer.Option(
            "--audit-hash-chain/--no-audit-hash-chain",
            help="Include SHA-256 hash-chain fields in audit events for tamper-evident-style review.",
        ),
    ] = True,
) -> None:
    """Generate an offline AI Vendor Exit Report."""
    commands.exit_report(
        baseline=baseline,
        candidate=candidate,
        input_file=input_file,
        output_file=output_file,
        fmt=fmt,
        title=title,
        workload=workload,
        risk_profile=risk_profile,
        min_quality_retention=min_quality_retention,
        max_latency_increase=max_latency_increase,
        min_cost_reduction=min_cost_reduction,
        export_aimeter=export_aimeter,
        export_auditlog=export_auditlog,
        run_id=run_id,
        system_id=system_id,
        actor=actor,
        audit_hash_chain=audit_hash_chain,
    )


@app.command("route-plan")
@guard
def route_plan(
    input_file: Annotated[Path, typer.Option("--input", help="Per-task route-plan JSON input.")],
    output_file: Annotated[Path, typer.Option("--output", help="Report output path.")],
    fmt: Annotated[str, typer.Option("--format", help="markdown|json")] = "markdown",
    baseline: Annotated[str, typer.Option("--baseline", help="Baseline provider:model, model, or label.")] = "baseline",
    candidate: Annotated[str, typer.Option("--candidate", help="Candidate provider:model, model, or label.")] = "candidate",
    workload: Annotated[str | None, typer.Option("--workload", help="Workload label.")] = None,
    risk_profile: Annotated[str, typer.Option("--risk-profile", help="low|medium|high|regulated")] = "medium",
    min_quality_retention: Annotated[
        float, typer.Option("--min-quality-retention", help="Minimum acceptable quality retention percentage.")
    ] = 80.0,
    max_latency_increase: Annotated[
        float, typer.Option("--max-latency-increase", help="Maximum acceptable latency increase percentage.")
    ] = 50.0,
    min_cost_reduction: Annotated[float, typer.Option("--min-cost-reduction", help="Minimum expected cost reduction percentage.")] = 20.0,
    export_json: Annotated[Path | None, typer.Option("--export-json", help="Write a machine-readable route-plan JSON file.")] = None,
    export_aimeter: Annotated[
        Path | None,
        typer.Option("--export-aimeter", help="Write an AIMeter OSS-style route cost/outcome summary JSON file."),
    ] = None,
    export_auditlog: Annotated[
        Path | None,
        typer.Option("--export-auditlog", help="Write AIAuditLog-style route audit events as JSONL."),
    ] = None,
    run_id: Annotated[str | None, typer.Option("--run-id", help="Run identifier for portable exports.")] = None,
    system_id: Annotated[str, typer.Option("--system-id", help="System identifier for audit events.")] = "modelswapbench",
    actor: Annotated[str, typer.Option("--actor", help="Actor identifier for audit events.")] = "modelswapbench-cli",
    audit_hash_chain: Annotated[
        bool,
        typer.Option(
            "--audit-hash-chain/--no-audit-hash-chain",
            help="Include SHA-256 hash-chain fields in audit events for tamper-evident-style review.",
        ),
    ] = True,
) -> None:
    """Generate an offline Model Routing Plan."""
    commands.route_plan(
        input_file=input_file,
        output_file=output_file,
        fmt=fmt,
        baseline=baseline,
        candidate=candidate,
        workload=workload,
        risk_profile=risk_profile,
        min_quality_retention=min_quality_retention,
        max_latency_increase=max_latency_increase,
        min_cost_reduction=min_cost_reduction,
        export_json=export_json,
        export_aimeter=export_aimeter,
        export_auditlog=export_auditlog,
        run_id=run_id,
        system_id=system_id,
        actor=actor,
        audit_hash_chain=audit_hash_chain,
    )


@app.command()
@guard
def reproduce(
    run_id: Annotated[str, typer.Argument(help="Run id or 'latest'.")],
    output_dir: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Re-run a stored suite; warns on version drift."""
    _run, code = commands.reproduce(run_id, output_dir)
    if code is not ExitCode.SUCCESS:
        raise typer.Exit(code=int(code))


@app.command()
@guard
def clean(
    run_id: Annotated[str, typer.Argument(help="Run id or 'latest'.")],
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation.")] = False,
    output_dir: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Delete a stored run (only under the storage directory)."""
    if not yes:
        typer.confirm(f"Delete run {run_id!r}? This cannot be undone.", abort=True)
    commands.clean(run_id, output_dir)


@app.command()
@guard
def init(
    name: Annotated[str, typer.Argument(help="New benchmark directory name.")] = "my-benchmark",
) -> None:
    """Scaffold a runnable, fully-offline starter benchmark."""
    commands_init(name)


@runs_app.command("list")
@guard
def runs_list(output_dir: Annotated[Path | None, typer.Option("--output")] = None) -> None:
    """List stored runs."""
    commands.runs_list(output_dir)


@runs_app.command("show")
@guard
def runs_show(run_id: str, output_dir: Annotated[Path | None, typer.Option("--output")] = None) -> None:
    """Show a stored run's metadata."""
    commands.runs_show(run_id, output_dir)


@pricing_app.command("show")
@guard
def pricing_show(path: Annotated[Path | None, typer.Option("--file")] = None) -> None:
    """Show the pricing registry."""
    commands.pricing_show(path)


@pricing_app.command("validate")
@guard
def pricing_validate(path: Annotated[Path | None, typer.Option("--file")] = None) -> None:
    """Validate the pricing registry."""
    code = commands.pricing_validate(path)
    if code is not ExitCode.SUCCESS:
        raise typer.Exit(code=int(code))


@pricing_app.command("set")
@guard
def pricing_set(
    model: str,
    provider: str,
    input_price: float,
    output_price: float,
    path: Annotated[Path, typer.Option("--file")] = Path("pricing.yaml"),
) -> None:
    """Set a price entry (writes to a user pricing file)."""
    commands.pricing_set(model, provider, input_price, output_price, path)


@examples_app.command("list")
@guard
def examples_list() -> None:
    """List bundled examples."""
    commands.examples_list()


@dataset_app.command("validate")
@guard
def dataset_validate(path: Annotated[Path, typer.Argument(help="Local dataset JSON or JSONL file.")]) -> None:
    """Strictly validate a private evaluation dataset."""
    commands.dataset_validate(path)


@dataset_app.command("inspect")
@guard
def dataset_inspect(path: Annotated[Path, typer.Argument(help="Local dataset JSON or JSONL file.")]) -> None:
    """Show bounded metadata and the deterministic dataset digest."""
    commands.dataset_inspect(path)


@dataset_app.command("digest")
@guard
def dataset_digest(path: Annotated[Path, typer.Argument(help="Local dataset JSON or JSONL file.")]) -> None:
    """Print the deterministic SHA-256 dataset digest."""
    commands.dataset_print_digest(path)


@dataset_app.command("create")
@guard
def dataset_create(
    output_file: Annotated[Path, typer.Option("--output", help="New .json or .jsonl dataset path.")],
    dataset_id: Annotated[str, typer.Option("--dataset-id", help="Stable dataset identifier.")] = "private-evaluation",
    name: Annotated[str, typer.Option("--name", help="Human-readable dataset name.")] = "Private evaluation dataset",
) -> None:
    """Create a local private-dataset template without personal identity."""
    commands.dataset_create(output_file, dataset_id=dataset_id, name=name)


@dataset_app.command("split")
@guard
def dataset_split(
    path: Annotated[Path, typer.Argument(help="Local dataset JSON or JSONL file.")],
    train: Annotated[int, typer.Option("--train", help="Deterministic training percentage.")] = 80,
    test: Annotated[int, typer.Option("--test", help="Deterministic evaluation percentage.")] = 20,
    train_output: Annotated[Path | None, typer.Option("--train-output")] = None,
    test_output: Annotated[Path | None, typer.Option("--test-output")] = None,
) -> None:
    """Create deterministic train/evaluation partitions; this does not prove generalization."""
    commands.dataset_split(
        path,
        train_percent=train,
        test_percent=test,
        train_output=train_output,
        test_output=test_output,
    )


@dataset_app.command("redact")
@guard
def dataset_redact(
    path: Annotated[Path, typer.Argument(help="Local dataset JSON or JSONL file.")],
    output_file: Annotated[Path, typer.Option("--output", help="Sanitized output path.")],
) -> None:
    """Mask common identifiers and credentials in a local dataset copy."""
    commands.dataset_redact(path, output_path=output_file)


@app.command("gate")
@guard
def gate_cmd(
    baseline: Annotated[Path, typer.Argument(help="Baseline gate artifact JSON.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate gate artifact JSON.")],
    thresholds: Annotated[Path | None, typer.Option("--thresholds", help="Gate threshold JSON.")] = None,
    fmt: Annotated[str, typer.Option("--format", help="console|json|markdown|github|junit")] = "console",
    output_file: Annotated[Path | None, typer.Option("--output", help="Write rendered gate output.")] = None,
) -> None:
    """Compare candidate evidence with a baseline and return a deterministic CI exit code."""
    code = commands.gate(baseline, candidate, thresholds_path=thresholds, fmt=fmt, output_path=output_file)
    if code is not ExitCode.SUCCESS:
        raise typer.Exit(code=int(code))


@outcomes_app.command("summarize")
@guard
def outcomes_summarize(
    path: Annotated[Path, typer.Argument(help="Local human-outcome JSONL file.")],
    output_file: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Aggregate pseudonymous human and business outcome labels."""
    commands.outcomes_summarize(path, output_path=output_file)


@workflow_app.command("evaluate")
@guard
def workflow_evaluate(
    path: Annotated[Path, typer.Argument(help="Workflow trace JSONL file.")],
    output_file: Annotated[Path, typer.Option("--output")],
    step_limit: Annotated[int, typer.Option("--step-limit", min=1, max=500)] = 100,
) -> None:
    """Evaluate complete multi-turn and tool workflows as decision units."""
    commands.workflow_evaluate(path, output_path=output_file, step_limit=step_limit)


@replay_app.command("sanitize")
@guard
def replay_sanitize(
    path: Annotated[Path, typer.Argument(help="Local replay JSONL file.")],
    output_file: Annotated[Path, typer.Option("--output")],
    preflight_file: Annotated[Path, typer.Option("--preflight-output")],
    provider_mode: Annotated[str, typer.Option("--provider-mode", help="local|self_hosted|hosted")] = "local",
    allow_hosted: Annotated[bool, typer.Option("--allow-hosted")] = False,
    omit_content: Annotated[bool, typer.Option("--omit-content")] = False,
    excerpt_length: Annotated[int, typer.Option("--excerpt-length", min=0, max=65_536)] = 2048,
) -> None:
    """Sanitize trace replay data and emit a provider/data-safety preflight."""
    commands.replay_sanitize(
        path,
        output_path=output_file,
        preflight_path=preflight_file,
        provider_mode=provider_mode,
        allow_hosted=allow_hosted,
        omit_content=omit_content,
        excerpt_length=excerpt_length,
    )


@telemetry_app.command("export")
@guard
def telemetry_export(
    path: Annotated[Path, typer.Argument(help="Workflow trace JSONL file.")],
    output_file: Annotated[Path, typer.Option("--output")],
    dataset_id: Annotated[str, typer.Option("--dataset-id")],
    dataset_digest: Annotated[str, typer.Option("--dataset-digest")],
    run_id: Annotated[str, typer.Option("--run-id")],
) -> None:
    """Export deterministic OpenTelemetry-compatible JSONL records."""
    commands.telemetry_export(
        path,
        output_path=output_file,
        dataset_id=dataset_id,
        dataset_digest_value=dataset_digest,
        run_id=run_id,
    )


_STARTER_SUITE = """name: {name}
version: "1.0"
description: Starter offline benchmark using the deterministic provider.
baseline_model: baseline

models:
  - alias: baseline
    provider: deterministic
    model: baseline-fixture
    deployment: test
    metadata: {{strategy: oracle, latency_ms: 20}}
  - alias: candidate
    provider: deterministic
    model: candidate-fixture
    deployment: local
    metadata: {{strategy: oracle, latency_ms: 5}}

cases:
  - id: greeting
    input: {{message: "Say hello and classify sentiment."}}
    expected: {{sentiment: positive}}

evaluators: [json_parse, json_schema, field_match]

constraints:
  minimum_success_rate: 0.8
  require_valid_json_rate: 0.9

replacement:
  baseline: baseline
  candidates: [candidate]
  maximum_quality_drop: 0.05
  minimum_cost_reduction: 0.0
"""


def commands_init(name: str) -> None:
    target = Path(name)
    target.mkdir(parents=True, exist_ok=True)
    suite_file = target / "benchmark.yaml"
    if suite_file.exists():
        output.warn(f"{suite_file} already exists; not overwriting")
        return
    suite_file.write_text(_STARTER_SUITE.format(name=name), encoding="utf-8")
    output.success(f"created {suite_file}")
    output.info(f"Next: modelswapbench validate {suite_file} && modelswapbench run {suite_file}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
