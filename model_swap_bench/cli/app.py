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
app.add_typer(runs_app, name="runs")
app.add_typer(pricing_app, name="pricing")
app.add_typer(examples_app, name="examples")

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
