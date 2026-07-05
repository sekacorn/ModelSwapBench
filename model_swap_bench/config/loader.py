"""Safe loading of benchmark suites from YAML/JSON files.

Only ``yaml.safe_load`` is used — benchmark files never execute arbitrary Python.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.config.models import BenchmarkSuite
from model_swap_bench.config.validation import validate_suite
from model_swap_bench.errors import ConfigError, ValidationError


def load_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML or JSON file into a plain mapping, safely."""
    if not path.exists():
        raise ConfigError(f"Benchmark file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            data: Any = json.loads(text)
        else:
            data = yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Could not parse {path.name}: {exc}") from exc
    if data is None:
        raise ConfigError(f"{path.name} is empty.")
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a mapping at the top level, got {type(data).__name__}.")
    return data


def _format_pydantic_error(exc: PydanticValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def build_suite(data: dict[str, Any]) -> BenchmarkSuite:
    """Validate a mapping into a :class:`BenchmarkSuite`, raising our error types."""
    try:
        suite = BenchmarkSuite.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError("Benchmark file failed schema validation:\n" + _format_pydantic_error(exc)) from exc
    validate_suite(suite)
    return suite


def load_suite(path: str | Path) -> BenchmarkSuite:
    """Load and fully validate a benchmark suite from a file path."""
    return build_suite(load_mapping(Path(path)))
