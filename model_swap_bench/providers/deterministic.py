"""Deterministic, offline provider for tests, CI, and no-download examples.

It never touches the network. Behavior is fully reproducible and can simulate
success, wrong answers, invalid JSON, tool calls, latency, token usage, and
failures — everything needed to exercise the evaluators and scoring offline.

Strategy is chosen via ``candidate.metadata['strategy']``:

- ``oracle``  — emit the case's expected output (a perfect model). Default.
- ``fixture`` — emit explicit per-case outputs from ``candidate.fixture`` file.
- ``static``  — emit a fixed string from ``candidate.metadata['output']``.

The ``fixture`` file (YAML/JSON, resolved relative to the suite directory)::

    default:
      latency_ms: 5
    cases:
      duplicate-billing:
        output: '{"category": "billing", "escalation_required": true}'
        latency_ms: 12
        tokens: {input: 40, output: 10}
        tool_calls: [{name: escalate, arguments: {}}]
        status: success      # or error / timeout
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.errors import ConfigError, ProviderResponseError
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse
from model_swap_bench.results import ToolCallRecord


class DeterministicProvider(Provider):
    """A reproducible, offline test provider."""

    kind = ProviderKind.DETERMINISTIC

    def __init__(self, candidate: ModelCandidate, *, suite_dir: Path | None = None) -> None:
        super().__init__(candidate)
        self._strategy = str(candidate.metadata.get("strategy", "fixture" if candidate.fixture else "oracle"))
        self._static_output = candidate.metadata.get("output")
        self._default_latency = float(candidate.metadata.get("latency_ms", 5.0))
        self._fixtures: dict[str, Any] = {}
        self._fixture_default: dict[str, Any] = {}
        if candidate.fixture:
            self._load_fixtures(candidate.fixture, suite_dir)

    def _load_fixtures(self, fixture: str, suite_dir: Path | None) -> None:
        path = Path(fixture)
        if not path.is_absolute() and suite_dir is not None:
            path = suite_dir / path
        if not path.exists():
            raise ConfigError(f"Deterministic fixture file not found for {self.alias!r}: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ConfigError(f"Fixture file {path} must contain a mapping.")
        self._fixture_default = dict(raw.get("default", {}))
        cases = raw.get("cases", {})
        self._fixtures = dict(cases) if isinstance(cases, dict) else {}

    async def health(self) -> HealthStatus:
        return HealthStatus(available=True, detail="deterministic provider is always available")

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        if self._strategy == "static":
            return self._respond(str(self._static_output or ""), self._default_latency)
        if self._strategy == "oracle":
            return self._oracle(request)
        return self._fixture(request)

    def _oracle(self, request: ProviderRequest) -> ProviderResponse:
        if request.expected is not None:
            text = json.dumps(request.expected)
        elif request.expected_text is not None:
            text = request.expected_text
        else:
            text = "OK"
        return self._respond(text, self._default_latency)

    def _fixture(self, request: ProviderRequest) -> ProviderResponse:
        case_id = request.case_id or ""
        spec = self._fixtures.get(case_id)
        if spec is None:
            # No explicit fixture for this case: behave as an oracle so partially
            # specified fixtures still produce a valid run.
            return self._oracle(request)
        if not isinstance(spec, dict):
            raise ConfigError(f"Fixture for case {case_id!r} must be a mapping.")
        status = str(spec.get("status", "success"))
        latency = float(spec.get("latency_ms", self._fixture_default.get("latency_ms", self._default_latency)))
        if status == "error":
            raise ProviderResponseError(f"deterministic fixture simulated an error for case {case_id!r}")
        if status == "timeout":
            from model_swap_bench.errors import ProviderTimeoutError

            raise ProviderTimeoutError(f"deterministic fixture simulated a timeout for case {case_id!r}")
        output = spec.get("output", "")
        text = output if isinstance(output, str) else json.dumps(output)
        tokens = spec.get("tokens", {}) or {}
        tool_calls = [
            ToolCallRecord(name=str(tc.get("name", "")), arguments=dict(tc.get("arguments", {})))
            for tc in spec.get("tool_calls", [])
            if isinstance(tc, dict)
        ]
        return self._respond(
            text,
            latency,
            input_tokens=int(tokens.get("input", 0)),
            output_tokens=int(tokens.get("output", 0)),
            tool_calls=tool_calls,
        )

    def _respond(
        self,
        text: str,
        latency_ms: float,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(
            text=text,
            tool_calls=tool_calls or [],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reported_model=self.candidate.model,
            execution_path="deterministic",
            endpoint=None,
            raw={"strategy": self._strategy, "simulated_latency_ms": latency_ms},
        )
