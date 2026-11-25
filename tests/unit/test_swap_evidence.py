"""``model-swap-evidence.v1``: what the writer emits, and what it refuses."""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from pydantic import ValidationError as PydanticValidationError
from typer.testing import CliRunner

from model_swap_bench import __version__
from model_swap_bench.cli.app import app
from model_swap_bench.config.models import DeploymentType, ProviderKind
from model_swap_bench.errors import ConfigError
from model_swap_bench.reports.swap_evidence import (
    MAX_TEXT_CHARS,
    ModelSwapEvidence,
    build_swap_evidence,
    endpoint_origin,
    render_swap_evidence_json,
    swap_evidence_json_schema,
)
from tests.conftest import make_suite_dict
from tests.unit.swap_evidence_fixtures import FIXTURE_DIR, VARIANTS, build, run_for

runner = CliRunner()
PLANTED = "sk-planted-value-0123456789"


def _packaged_schema() -> dict[str, Any]:
    resource = files("model_swap_bench").joinpath("resources/model-swap-evidence.schema.json")
    loaded: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
    return loaded


def _document(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(render_swap_evidence_json(build(name)))
    return loaded


# --- the format ---------------------------------------------------------------


def test_the_packaged_schema_matches_the_models() -> None:
    assert _packaged_schema() == swap_evidence_json_schema()


def test_the_schema_is_closed_at_every_level() -> None:
    schema = _packaged_schema()
    objects = [schema, *schema["$defs"].values()]
    typed = [node for node in objects if node.get("type") == "object"]
    assert len(typed) >= 8
    assert all(node.get("additionalProperties") is False for node in typed)
    assert schema["properties"]["schema_version"]["const"] == "model-swap-evidence.v1"


@pytest.mark.parametrize("name", VARIANTS)
def test_every_variant_validates_against_the_packaged_schema(name: str) -> None:
    jsonschema.Draft202012Validator(_packaged_schema(), format_checker=jsonschema.FormatChecker()).validate(_document(name))


@pytest.mark.parametrize("name", VARIANTS)
def test_every_committed_fixture_is_what_the_writer_produces(name: str) -> None:
    committed = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    # The producer version moves with every release; nothing else may differ.
    committed["generated_by"]["version"] = __version__
    assert committed == _document(name)


def test_there_is_a_fixture_for_every_variant_and_no_stray_one() -> None:
    assert sorted(path.stem for path in FIXTURE_DIR.glob("*.json")) == sorted(VARIANTS)


def test_rendering_is_deterministic_and_round_trips() -> None:
    first = render_swap_evidence_json(build("tools-and-policy"))
    assert first == render_swap_evidence_json(build("tools-and-policy"))
    assert first.endswith("\n")
    assert ModelSwapEvidence.model_validate_json(first) == build("tools-and-policy")
    assert json.loads(first)["run"]["created_at"] == "2026-11-25T12:00:00Z"


# --- what each field carries --------------------------------------------------


def test_only_the_origin_of_an_endpoint_is_written() -> None:
    document = _document("hosted-accepted")
    assert document["baseline"]["endpoint_origin"] == "https://llm.vendor-a.example"
    # Host lower-cased, port kept, path dropped.
    assert document["candidate"]["endpoint_origin"] == "https://api.vendor-b.example:8443"
    assert "/v1" not in json.dumps(document)


def test_ipv6_default_and_absent_endpoints() -> None:
    assert _document("self-hosted-ipv6")["candidate"]["endpoint_origin"] == "http://[fd00::10]:8000"
    assert _document("default-endpoint")["candidate"]["endpoint_origin"] == "http://localhost:11434"
    fake = _document("fake-candidate")["candidate"]
    assert fake["endpoint_origin"] is None
    assert (fake["provider_kind"], fake["deployment_declared"]) == ("deterministic", "test")


def test_the_declared_deployment_is_reported_as_declared() -> None:
    assert _document("self-hosted-ipv6")["candidate"]["deployment_declared"] == "self_hosted"
    assert _document("hosted-accepted")["candidate"]["deployment_declared"] == "hosted"


def test_counts_and_rates_come_straight_from_the_summary() -> None:
    summary = _document("not-recommended")["candidate"]["summary"]
    assert (summary["sample_count"], summary["success_count"], summary["failure_count"]) == (24, 15, 7)
    assert (summary["error_count"], summary["timeout_count"]) == (1, 1)
    assert summary["quality_score"] == 0.61
    assert summary["tool_accuracy"] is None
    assert summary["policy_pass_rate"] is None


def test_missing_policy_and_tool_evidence_stays_null_never_a_pass() -> None:
    document = _document("local-accepted")
    assert document["candidate"]["summary"]["policy_pass_rate"] is None
    assert document["candidate"]["summary"]["tool_accuracy"] is None
    assert document["verdict"]["policy_pass"] is False


def test_quality_is_null_when_nothing_executed() -> None:
    document = _document("nothing-executed")
    assert document["candidate"]["summary"]["quality_score"] is None
    assert document["verdict"] == {
        "recommendation": "insufficient evidence",
        "eligible": False,
        "policy_pass": False,
        "deployment_compatible": True,
    }


def test_the_verdict_is_the_decision_engines_own() -> None:
    for name in VARIANTS:
        run, _suite, _alias = run_for(name)
        decision = run.replacement_decisions[0]
        verdict = _document(name)["verdict"]
        assert verdict["recommendation"] == decision.recommendation
        assert verdict["eligible"] is decision.eligible
    assert _document("insufficient-samples")["candidate"]["summary"]["evidence_sufficient"] is False
    assert _document("policy-failed")["verdict"]["recommendation"] == "not recommended"


def test_thresholds_and_constraints_are_recorded() -> None:
    document = _document("tools-and-policy")
    assert document["thresholds"] == {
        "maximum_quality_drop": 0.05,
        "minimum_reliability": 0.9,
        "maximum_latency_ms": 2000.0,
        "minimum_cost_reduction": 0.2,
        "hosted_candidates_permitted": True,
    }
    assert document["candidate_constraints"] == [
        {"name": "minimum_tool_accuracy", "passed": True},
        {"name": "require_policy_pass", "passed": True},
    ]
    assert _document("not-recommended")["candidate_constraints"] == [{"name": "minimum_success_rate", "passed": False}]


def test_the_document_carries_no_cost_cases_or_free_text() -> None:
    text = json.dumps(_document("not-recommended"))
    for absent in ("cost_usd", "case_id", "raw_output", 'error"', 'evidence"', "risks", "api_key", "VENDOR_A_API_KEY"):
        assert absent not in text


# --- what the writer refuses --------------------------------------------------


def test_a_run_without_a_replacement_section_is_refused() -> None:
    run, suite, alias = run_for("local-accepted")
    bare = suite.model_copy(update={"replacement": None})
    with pytest.raises(ConfigError, match="no replacement section"):
        build_swap_evidence(run, bare, alias)


def test_an_unknown_candidate_is_refused() -> None:
    run, suite, _alias = run_for("local-accepted")
    with pytest.raises(ConfigError, match="no replacement decision"):
        build_swap_evidence(run, suite, "current")
    with pytest.raises(ConfigError, match="no replacement decision"):
        build_swap_evidence(run, suite, "nobody")


def test_a_run_that_was_never_stored_is_refused() -> None:
    run, suite, alias = run_for("local-accepted")
    with pytest.raises(ConfigError, match="no manifest hash"):
        build_swap_evidence(run.model_copy(update={"manifest_hash": ""}), suite, alias)


def test_an_unknown_recommendation_is_refused() -> None:
    run, suite, alias = run_for("local-accepted")
    decision = run.replacement_decisions[0].model_copy(update={"recommendation": "ship it"})
    with pytest.raises(ConfigError, match="does not know"):
        build_swap_evidence(run.model_copy(update={"replacement_decisions": [decision]}), suite, alias)


def test_missing_results_for_a_side_are_refused() -> None:
    run, suite, alias = run_for("local-accepted")
    with pytest.raises(ConfigError, match="no results for its baseline"):
        build_swap_evidence(run.model_copy(update={"model_summaries": run.model_summaries[1:]}), suite, alias)


@pytest.mark.parametrize(
    ("field", "value", "where"),
    [
        ("quality_score", 1.5, "candidate.summary.quality_score"),
        ("quality_score", float("nan"), "candidate.summary.quality_score"),
        ("tool_accuracy", -0.1, "candidate.summary.tool_accuracy"),
        ("policy_pass_rate", 2.0, "candidate.summary.policy_pass_rate"),
        ("p95_latency_ms", float("inf"), "candidate.summary.p95_latency_ms"),
        ("total_cases", -1, "candidate.summary.sample_count"),
        ("minimum_recommended_sample_size", 0, "candidate.summary.minimum_recommended_sample_size"),
    ],
)
def test_out_of_range_numbers_are_refused_and_named(field: str, value: float, where: str) -> None:
    run, suite, alias = run_for("local-accepted")
    broken = run.model_summaries[1].model_copy(update={field: value})
    with pytest.raises(ConfigError, match="out of bounds") as excinfo:
        build_swap_evidence(run.model_copy(update={"model_summaries": [run.model_summaries[0], broken]}), suite, alias)
    assert where in str(excinfo.value)


def test_an_overlong_model_name_is_refused_without_being_repeated() -> None:
    run, suite, alias = run_for("local-accepted")
    long_name = PLANTED * 20
    assert len(long_name) > MAX_TEXT_CHARS
    models = [suite.models[0], suite.models[1].model_copy(update={"model": long_name})]
    with pytest.raises(ConfigError) as excinfo:
        build_swap_evidence(run, suite.model_copy(update={"models": models}), alias)
    assert "candidate.model" in str(excinfo.value)
    assert PLANTED not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


def test_too_many_constraints_are_refused() -> None:
    run, suite, alias = run_for("not-recommended")
    many = run.constraint_results[alias] * 17
    with pytest.raises(ConfigError, match="candidate_constraints"):
        build_swap_evidence(run.model_copy(update={"constraint_results": {alias: many}}), suite, alias)


@pytest.mark.parametrize(
    "url",
    [
        f"https://user:{PLANTED}@host.example/v1",
        "ftp://host.example",
        "https://",
        "host.example/v1",
        "http://[::1",
        "https://host_name.example",
        "https://host.example:99999",
    ],
)
def test_a_url_that_is_not_a_plain_http_origin_is_refused_without_being_repeated(url: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        endpoint_origin(url)
    assert str(excinfo.value) == "a model's base_url cannot be reduced to an origin."
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("HTTPS://Host.Example/v1/chat?x", "https://host.example"),
        ("http://localhost:8000/", "http://localhost:8000"),
        ("http://[::1]:11434/api", "http://[::1]:11434"),
        ("http://10.0.0.5", "http://10.0.0.5"),
    ],
)
def test_origin_reduction(url: str, origin: str) -> None:
    assert endpoint_origin(url) == origin


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version="model-swap-evidence.v2"),
        lambda d: d.update(extra="x"),
        lambda d: d["candidate"].update(endpoint_origin="https://host.example/v1"),
        lambda d: d["candidate"].update(endpoint_origin="https://user@host.example"),
        lambda d: d["candidate"]["summary"].update(notes="x"),
        lambda d: d["run"].update(manifest_hash="abc"),
        lambda d: d["verdict"].update(recommendation="ship it"),
        lambda d: d["generated_by"].update(tool="something-else"),
        lambda d: d.pop("thresholds"),
    ],
)
def test_the_model_and_the_schema_refuse_the_same_malformed_documents(mutate: Any) -> None:
    document = _document("hosted-accepted")
    mutate(document)
    with pytest.raises(PydanticValidationError):
        ModelSwapEvidence.model_validate(document)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(_packaged_schema()).validate(document)


# --- the command --------------------------------------------------------------


def _stored_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    monkeypatch.chdir(tmp_path)
    suite_file = tmp_path / "b.yaml"
    suite_file.write_text(yaml.safe_dump(make_suite_dict(**overrides)), encoding="utf-8")
    assert runner.invoke(app, ["run", str(suite_file)]).exit_code == 0


def test_the_command_writes_a_valid_document_for_a_stored_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_run(tmp_path, monkeypatch)
    out = tmp_path / "evidence" / "swap.json"
    result = runner.invoke(app, ["swap-evidence", "latest", "--output", str(out)])
    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(_packaged_schema(), format_checker=jsonschema.FormatChecker()).validate(document)
    assert document["candidate"]["alias"] == "candidate"
    assert document["baseline"]["alias"] == "baseline"
    assert document["candidate"]["summary"]["sample_count"] == 2
    assert document["candidate"]["summary"]["evidence_sufficient"] is False
    assert document["verdict"]["recommendation"] == "insufficient evidence"
    # Bound to the stored run: the hash is the one stored beside it.
    stored = json.loads(next((tmp_path / ".modelswapbench" / "runs").glob("*/run.json")).read_text(encoding="utf-8"))
    assert document["run"]["manifest_hash"] == stored["manifest_hash"]
    assert document["run"]["run_id"] == stored["run_id"]


def test_the_command_prints_plain_json_without_an_output_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_run(tmp_path, monkeypatch)
    result = runner.invoke(app, ["swap-evidence", "--candidate", "candidate"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["schema_version"] == "model-swap-evidence.v1"


def test_the_command_refuses_an_unknown_candidate_and_a_run_that_compared_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_run(tmp_path, monkeypatch)
    assert runner.invoke(app, ["swap-evidence", "--candidate", "nobody"]).exit_code != 0
    assert runner.invoke(app, ["swap-evidence", "no-such-run"]).exit_code != 0


def test_the_command_needs_a_candidate_named_when_there_is_not_exactly_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stored_run(tmp_path, monkeypatch, replacement=None)
    result = runner.invoke(app, ["swap-evidence"])
    assert result.exit_code != 0
    assert "--candidate" in result.output


# --- a side declared local at an endpoint that is not local ---------------------


def _with_candidate(name: str, **update: Any) -> tuple[Any, Any, str]:
    run, suite, alias = run_for(name)
    models = [suite.models[0], suite.models[1].model_copy(update=update)]
    return run, suite.model_copy(update={"models": models}), alias


@pytest.mark.parametrize(
    "update",
    [
        {"base_url": "https://gpu.vendor-c.example/v1"},
        {"base_url": "http://ollama.internal:11434"},
        {"base_url": "http://100.64.0.1:11434"},
    ],
)
def test_a_candidate_declared_local_at_a_host_that_is_not_local_is_refused(update: dict[str, Any]) -> None:
    run, suite, alias = _with_candidate("local-accepted", **update)
    with pytest.raises(ConfigError, match="declared local but its endpoint is not local") as excinfo:
        build_swap_evidence(run, suite, alias)
    assert "vendor-c" not in str(excinfo.value)
    assert "ollama.internal" not in str(excinfo.value)


def test_a_vendor_sdk_declared_local_with_no_endpoint_is_refused() -> None:
    run, suite, alias = _with_candidate("local-accepted", provider=ProviderKind.ANTHROPIC, base_url=None)
    with pytest.raises(ConfigError, match="candidate model is declared local"):
        build_swap_evidence(run, suite, alias)


def test_the_baseline_is_held_to_the_same_rule() -> None:
    run, suite, alias = run_for("local-accepted")
    baseline = suite.models[0].model_copy(update={"deployment": DeploymentType.LOCAL})
    with pytest.raises(ConfigError, match="baseline model is declared local"):
        build_swap_evidence(run, suite.model_copy(update={"models": [baseline, suite.models[1]]}), alias)


@pytest.mark.parametrize("deployment", [DeploymentType.SELF_HOSTED, DeploymentType.HOSTED])
def test_self_hosted_or_hosted_at_a_public_host_is_written(deployment: DeploymentType) -> None:
    run, suite, alias = _with_candidate("local-accepted", base_url="https://gpu.vendor-c.example/v1", deployment=deployment)
    document = json.loads(render_swap_evidence_json(build_swap_evidence(run, suite, alias)))
    assert document["candidate"]["deployment_declared"] == deployment.value
    assert document["candidate"]["endpoint_origin"] == "https://gpu.vendor-c.example"


def test_a_deterministic_fixture_declared_local_is_written() -> None:
    run, suite, alias = _with_candidate("fake-candidate", deployment=DeploymentType.LOCAL)
    assert build_swap_evidence(run, suite, alias).candidate.deployment_declared is DeploymentType.LOCAL
