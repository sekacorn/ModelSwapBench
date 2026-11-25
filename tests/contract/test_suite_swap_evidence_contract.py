"""Every swap-evidence document this package emits must be readable by the suite.

ModelSwapBench and the AI Infrastructure Suite take no code dependency on each
other; the contract between them is the ``model-swap-evidence.v1`` document,
and **the suite's schema is canonical**. This package's own schema may be
narrower, never wider: a document this writer emits that the suite's schema or
reader refuses is a bug here.

Not part of the offline unit suite: it needs ``ai-infrastructure-suite``
installed, which the ``suite-contract`` CI job does from the suite's main
branch. Without it every test here skips, so the offline matrix stays offline.
CI sets ``MODELSWAPBENCH_REQUIRE_SUITE_CONTRACT=1`` so a missing suite fails
instead of passing a check that never ran.

Both halves are checked because they fail differently: the schema enforces
the closed field inventory; the reader enforces cross-field consistency and
refuses a verdict that disagrees with the numbers.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any, Final

import pytest

from model_swap_bench.reports.swap_evidence import render_swap_evidence_json
from tests.unit.swap_evidence_fixtures import VARIANTS, build

REQUIRE_ENV: Final = "MODELSWAPBENCH_REQUIRE_SUITE_CONTRACT"


def _import_or_skip(module: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError:
        if os.environ.get(REQUIRE_ENV) == "1":
            pytest.fail(
                f"ai-infrastructure-suite with {module} is not installed and {REQUIRE_ENV}=1; "
                "a skip here would report success for a check that never ran."
            )
        pytest.skip(f"{module} is not installed; set {REQUIRE_ENV}=1 to make this a failure.", allow_module_level=True)


reader = _import_or_skip("ai_infrastructure_suite.model_swap_evidence")
jsonschema = _import_or_skip("jsonschema")


def _suite_schema() -> dict[str, Any]:
    from importlib.resources import files

    text = files("ai_infrastructure_suite").joinpath("data/model-swap-evidence.schema.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def test_the_suite_ships_the_canonical_schema() -> None:
    schema = _suite_schema()
    assert schema["properties"]["schema_version"]["const"] == "model-swap-evidence.v1"


@pytest.mark.parametrize("name", VARIANTS)
def test_every_emitted_variant_validates_against_the_suites_schema(name: str) -> None:
    document = json.loads(render_swap_evidence_json(build(name)))
    errors = [error.message for error in jsonschema.Draft202012Validator(_suite_schema()).iter_errors(document)]
    assert errors == []


@pytest.mark.parametrize("name", VARIANTS)
def test_every_emitted_variant_is_accepted_by_the_suites_reader(name: str) -> None:
    text = render_swap_evidence_json(build(name))
    evidence = reader.parse_model_swap_evidence(text.encode("utf-8"))
    # The reader recomputes the verdict; agreeing with ours is the contract.
    assert evidence.verdict.eligible is build(name).verdict.eligible
    assert evidence.verdict.recommendation == build(name).verdict.recommendation


def test_the_vendored_locality_table_equals_the_suites() -> None:
    from importlib.resources import files
    from pathlib import Path

    suite_table = json.loads(files("ai_infrastructure_suite").joinpath("data/endpoint-locality-cases.json").read_text(encoding="utf-8"))
    vendored = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "endpoint-locality-cases.json").read_text(encoding="utf-8"))
    assert vendored == suite_table


def test_this_rule_agrees_with_the_suites_rule_on_every_case() -> None:
    from importlib.resources import files

    from model_swap_bench.endpoints import endpoint_is_local

    inventory = _import_or_skip("ai_infrastructure_suite.provider_inventory")
    table = json.loads(files("ai_infrastructure_suite").joinpath("data/endpoint-locality-cases.json").read_text(encoding="utf-8"))
    for case in table["cases"]:
        assert endpoint_is_local(case["url"]) is inventory.origin_is_local(case["url"]) is case["local"], case["url"]
