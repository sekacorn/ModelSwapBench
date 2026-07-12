from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from model_swap_bench.cli.app import app
from model_swap_bench.cli.commands import run
from model_swap_bench.errors import ExitCode
from tests.conftest import make_suite_dict

runner = CliRunner()


def _write_suite(path: Path) -> Path:
    path.write_text(yaml.safe_dump(make_suite_dict()), encoding="utf-8")
    return path


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "modelswapbench" in result.stdout


def test_providers_and_schema_and_examples() -> None:
    assert runner.invoke(app, ["providers"]).exit_code == 0
    assert runner.invoke(app, ["schema"]).exit_code == 0
    assert runner.invoke(app, ["examples", "list"]).exit_code == 0


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0  # environment is healthy enough (warnings allowed)


def test_validate_and_models(tmp_path: Path) -> None:
    suite_file = _write_suite(tmp_path / "b.yaml")
    assert runner.invoke(app, ["validate", str(suite_file)]).exit_code == 0
    assert runner.invoke(app, ["models", str(suite_file)]).exit_code == 0


def test_validate_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nmodels: []\ncases: []\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 2  # invalid input


def test_run_report_compare(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    suite_file = _write_suite(tmp_path / "b.yaml")
    run_result = runner.invoke(app, ["run", str(suite_file)])
    assert run_result.exit_code == 0
    assert runner.invoke(app, ["compare", "latest"]).exit_code == 0
    assert runner.invoke(app, ["report", "latest", "--format", "json"]).exit_code == 0
    assert runner.invoke(app, ["runs", "list"]).exit_code == 0


def test_run_dry_run(tmp_path: Path) -> None:
    suite_file = _write_suite(tmp_path / "b.yaml")
    result = runner.invoke(app, ["run", str(suite_file), "--dry-run"])
    assert result.exit_code == 0


def test_dry_run_respects_privacy_gate_for_external_openai_compatible(tmp_path: Path) -> None:
    suite_file = tmp_path / "external.json"
    suite_file.write_text(
        json.dumps(
            {
                "name": "privacy-dry-run",
                "models": [
                    {
                        "alias": "external",
                        "provider": "openai_compatible",
                        "model": "example",
                        "deployment": "self_hosted",
                        "base_url": "https://api.example.com/v1",
                    }
                ],
                "cases": [{"id": "c1", "input": {"message": "hi"}}],
                "privacy": {"allow_hosted_providers": False},
            }
        ),
        encoding="utf-8",
    )

    _run, code = run(suite_file, allow_hosted=True, dry_run=True)

    assert code is ExitCode.PROVIDER_UNAVAILABLE


def test_pricing_show_and_validate() -> None:
    assert runner.invoke(app, ["pricing", "show"]).exit_code == 0
    assert runner.invoke(app, ["pricing", "validate"]).exit_code == 0
