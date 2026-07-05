"""Execution context: prompt construction and per-call request building.

Prompt construction is deliberately simple and provider-neutral. Only the output
*format* (field names) is revealed to the model — never the expected values —
so structured-output workflows are testable without leaking answers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from model_swap_bench.config.models import BenchmarkCase, BenchmarkSuite, ModelCandidate
from model_swap_bench.providers.base import ProviderRequest


def render_input(case: BenchmarkCase) -> str:
    """Render a case's structured input into a prompt body."""
    if case.prompt:
        return case.prompt
    if not case.input:
        return case.description or "Complete the task."
    if set(case.input.keys()) == {"message"}:
        return str(case.input["message"]).strip()
    return json.dumps(case.input, indent=2)


def expected_field_names(case: BenchmarkCase) -> list[str]:
    names: list[str] = list(case.required_fields)
    if case.expected:
        names.extend(k for k in case.expected if k not in names)
    if case.expected_schema:
        for k in case.expected_schema.get("properties", {}):
            if k not in names:
                names.append(k)
    return names


def build_system_prompt(case: BenchmarkCase) -> str | None:
    """Construct instructions that describe the required output shape (not its values)."""
    fields = expected_field_names(case)
    parts = ["You are a workflow assistant. Follow the task precisely."]
    if fields or case.expected is not None or case.expected_schema is not None:
        parts.append("Respond with a single JSON object and nothing else.")
        if fields:
            parts.append("Include exactly these keys: " + ", ".join(fields) + ".")
    return " ".join(parts)


@dataclass
class ExecutionContext:
    """Shared configuration for one benchmark run."""

    suite: BenchmarkSuite
    run_id: str
    allow_hosted: bool = False
    max_tokens: int = 1024

    def build_request(self, model: ModelCandidate, case: BenchmarkCase) -> ProviderRequest:
        timeout = (
            case.timeout_override
            or model.timeout_seconds
            or self.suite.execution.timeout_seconds
        )
        tools = list(dict.fromkeys([*case.expected_tool_calls, *case.forbidden_tools]))
        return ProviderRequest(
            model_id=model.model,
            prompt=render_input(case),
            system=build_system_prompt(case),
            temperature=model.temperature,
            seed=model.seed if model.seed is not None else self.suite.execution.seed,
            max_tokens=self.max_tokens,
            timeout_seconds=timeout,
            available_tools=tools,
            case_id=case.id,
            expected=case.expected,
            expected_text=case.expected_text,
        )
