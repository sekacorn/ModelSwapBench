from __future__ import annotations

from pathlib import Path

import pytest

from model_swap_bench.errors import SecurityError
from model_swap_bench.security.paths import resolve_within, validate_run_id
from model_swap_bench.security.redaction import redact_text, redact_value


def test_validate_run_id_rejects_traversal() -> None:
    for bad in ["../etc", "a/b", "a\\b", "..", "with space"]:
        with pytest.raises(SecurityError):
            validate_run_id(bad)
    assert validate_run_id("run-20260101-000000-abc123") == "run-20260101-000000-abc123"


def test_resolve_within_blocks_escape(tmp_path: Path) -> None:
    assert resolve_within(tmp_path, "runs", "r1").name == "r1"
    with pytest.raises(SecurityError):
        resolve_within(tmp_path, "..", "..", "etc")


def test_redact_text() -> None:
    secret = "key sk-ABCDEFGHIJKLMNOP1234567890 here"
    assert "sk-ABCDEFGH" not in redact_text(secret)
    bearer = "Authorization: Bearer abcdef1234567890ABCDEF"
    assert "abcdef1234567890" not in redact_text(bearer)


def test_redact_value_sensitive_keys() -> None:
    data = {"api_key": "supersecret", "nested": {"password": "p", "ok": "value"}}
    red = redact_value(data)
    assert red["api_key"] != "supersecret"
    assert red["nested"]["password"] != "p"
    assert red["nested"]["ok"] == "value"


def test_yaml_safe_load_no_code_execution(tmp_path: Path) -> None:
    # Ensures benchmark loading never executes arbitrary python objects.
    from model_swap_bench.config.loader import load_mapping
    from model_swap_bench.errors import ConfigError

    evil = tmp_path / "evil.yaml"
    evil.write_text("!!python/object/apply:os.system ['echo pwned']\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_mapping(evil)
