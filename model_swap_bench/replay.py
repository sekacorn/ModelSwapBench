"""Local-only sanitized production trace replay contracts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench.errors import ConfigError
from model_swap_bench.portable import bounded_diagnostic, canonical_json, load_json, read_bounded_text
from model_swap_bench.security.redaction import redact_value

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)


class ReplayTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    trace_id: str = Field(min_length=1, max_length=256)
    case_id: str = Field(min_length=1, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)
    request_messages: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    response_messages: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    tool_results: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    retrieval_summaries: list[str] = Field(default_factory=list, max_length=100)
    model_requested: str | None = Field(default=None, max_length=512)
    model_used: str | None = Field(default=None, max_length=512)
    provider: str | None = Field(default=None, max_length=256)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=4096)
    timeout: bool = False
    human_outcome: str | None = Field(default=None, max_length=256)
    risk_level: str = Field(default="unknown", max_length=64)
    privacy_classification: str = Field(default="unknown", max_length=64)


class ReplayPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_count: int
    sensitive_content_found: bool
    redaction_applied: bool
    provider_mode: str
    hosted_execution_enabled: bool
    content_leaves_machine: bool
    findings: dict[str, int]
    warnings: list[str] = Field(default_factory=list)


def load_replay_jsonl(path: Path) -> list[ReplayTrace]:
    traces: list[ReplayTrace] = []
    for line_number, line in enumerate(read_bounded_text(path, max_bytes=20 * 1024 * 1024).splitlines(), 1):
        if not line.strip():
            continue
        try:
            traces.append(ReplayTrace.model_validate(load_json(line, source=f"{path.name}:{line_number}")))
        except PydanticValidationError as exc:
            raise ConfigError(f"invalid replay trace at line {line_number}: {bounded_diagnostic(exc)}") from exc
    return traces


def _sanitize_text(text: str, findings: dict[str, int], *, omit_content: bool, excerpt_length: int) -> str:
    if _PRIVATE_KEY.search(text):
        findings["private_keys"] += 1
        text = _PRIVATE_KEY.sub("[redacted-private-key]", text)
    email_count = len(_EMAIL.findall(text))
    phone_matches = [match for match in _PHONE.finditer(text) if sum(character.isdigit() for character in match.group()) >= 10]
    phone_count = len(phone_matches)
    findings["emails"] += email_count
    findings["phone_numbers"] += phone_count
    text = _EMAIL.sub("[redacted-email]", text)
    text = _PHONE.sub(
        lambda match: "[redacted-phone]" if sum(character.isdigit() for character in match.group()) >= 10 else match.group(),
        text,
    )
    redacted = redact_value(text)
    if redacted != text:
        findings["credentials_or_tokens"] += 1
    if omit_content:
        return "[content-omitted]"
    return str(redacted)[:excerpt_length]


def _sanitize_value(value: Any, findings: dict[str, int], *, omit_content: bool, excerpt_length: int) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value, findings, omit_content=omit_content, excerpt_length=excerpt_length)
    if isinstance(value, list):
        return [_sanitize_value(item, findings, omit_content=omit_content, excerpt_length=excerpt_length) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_value(item, findings, omit_content=omit_content, excerpt_length=excerpt_length) for key, item in value.items()
        }
    return value


def sanitize_replay(
    traces: list[ReplayTrace], *, salt: str = "modelswapbench-replay-v1", omit_content: bool = False, excerpt_length: int = 2048
) -> tuple[list[ReplayTrace], dict[str, int]]:
    if excerpt_length < 0 or excerpt_length > 65_536:
        raise ConfigError("excerpt length must be between 0 and 65536")
    findings = {"emails": 0, "phone_numbers": 0, "credentials_or_tokens": 0, "private_keys": 0}
    sanitized: list[ReplayTrace] = []
    for trace in traces:
        payload = trace.model_dump(mode="json")
        for field_name in (
            "request_messages",
            "response_messages",
            "tool_calls",
            "tool_results",
            "retrieval_summaries",
            "error",
        ):
            payload[field_name] = _sanitize_value(
                payload[field_name],
                findings,
                omit_content=omit_content,
                excerpt_length=excerpt_length,
            )
        payload["trace_id"] = hashlib.sha256(f"{salt}:trace:{trace.trace_id}".encode()).hexdigest()[:24]
        payload["case_id"] = hashlib.sha256(f"{salt}:case:{trace.case_id}".encode()).hexdigest()[:24]
        if trace.task_id:
            payload["task_id"] = hashlib.sha256(f"{salt}:task:{trace.task_id}".encode()).hexdigest()[:24]
        sanitized.append(ReplayTrace.model_validate(payload))
    return sanitized, findings


def build_replay_preflight(
    traces: list[ReplayTrace], findings: dict[str, int], *, provider_mode: str, hosted_execution_enabled: bool, redaction_applied: bool
) -> ReplayPreflight:
    sensitive = any(findings.values()) or any(trace.privacy_classification not in {"public", "unknown"} for trace in traces)
    hosted = provider_mode == "hosted"
    warnings: list[str] = []
    if hosted and not hosted_execution_enabled:
        warnings.append("hosted replay is blocked until explicitly enabled")
    if hosted and sensitive and not redaction_applied:
        warnings.append("sensitive trace content could leave the machine")
    return ReplayPreflight(
        trace_count=len(traces),
        sensitive_content_found=sensitive,
        redaction_applied=redaction_applied,
        provider_mode=provider_mode,
        hosted_execution_enabled=hosted_execution_enabled,
        content_leaves_machine=hosted and hosted_execution_enabled,
        findings=findings,
        warnings=warnings,
    )


def render_replay_jsonl(traces: list[ReplayTrace]) -> str:
    return "\n".join(canonical_json(trace.model_dump(mode="json")) for trace in traces) + ("\n" if traces else "")
