"""Secret redaction for logs, results, and reports.

Applied before anything is written to disk or rendered. API keys are read from
the environment and never enter results in the first place; this is defense in
depth against tokens leaking via raw model output or error strings.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = "«redacted»"

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),          # OpenAI-style keys
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b"),   # bearer tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),   # slack-style
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),               # AWS access key id
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),           # github token
]

_SENSITIVE_KEYS = frozenset({"api_key", "apikey", "authorization", "password", "secret", "token"})


def redact_text(text: str) -> str:
    """Mask secret-looking substrings in a string."""
    for pattern in _PATTERNS:
        text = pattern.sub(_PLACEHOLDER, text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively redact secrets in strings, dicts, and lists."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: (_PLACEHOLDER if str(k).lower() in _SENSITIVE_KEYS else redact_value(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
