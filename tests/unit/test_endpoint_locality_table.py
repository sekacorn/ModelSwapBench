"""This package's copy of the locality rule against the shared case table.

The table is the AI Infrastructure Suite's ``endpoint-locality-cases.v1``,
vendored here so the check runs offline. The ``suite-contract`` job proves this
copy still equals the suite's canonical one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from model_swap_bench.endpoints import endpoint_is_local

TABLE = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "endpoint-locality-cases.json").read_text(encoding="utf-8"))


def test_the_vendored_table_is_the_v1_format() -> None:
    assert TABLE["schema_version"] == "endpoint-locality-cases.v1"


@pytest.mark.parametrize("case", TABLE["cases"], ids=lambda case: case["url"])
def test_endpoint_is_local_agrees_with_every_case(case: dict[str, Any]) -> None:
    assert endpoint_is_local(case["url"]) is case["local"], case["why"]
