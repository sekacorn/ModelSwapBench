"""``modelswapbench doctor`` — read-only environment diagnostics (never modifies the system)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

from model_swap_bench._version import __version__
from model_swap_bench.config.schema import benchmark_json_schema
from model_swap_bench.providers.ollama import DEFAULT_BASE_URL

PASS = "pass"
WARN = "warning"
FAIL = "fail"
NA = "not applicable"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _python_check() -> Check:
    major, minor = sys.version_info[:2]
    if major == 3 and minor in (11, 12, 13):
        return Check("python version", PASS, f"{major}.{minor} is supported")
    return Check("python version", FAIL, f"{major}.{minor} unsupported", "use Python 3.11, 3.12, or 3.13")


def _forge_check() -> Check:
    try:
        import importlib.metadata as md

        return Check("agentforge-oss", PASS, f"installed {md.version('agentforge-oss')}")
    except Exception:  # noqa: BLE001
        return Check("agentforge-oss", FAIL, "not installed", "reinstall modelswapbench with its dependencies")


def _ollama_check(base_url: str) -> tuple[Check, set[str]]:
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return (
            Check("ollama endpoint", WARN, f"not reachable at {base_url}", "start Ollama, or run offline examples"),
            set(),
        )
    names = {m.get("name", "") for m in resp.json().get("models", [])}
    return Check("ollama endpoint", PASS, f"reachable at {base_url}; {len(names)} model(s)"), names


def _model_check(models: set[str], reachable: bool, wanted: str = "qwen2.5:3b") -> Check:
    if not reachable:
        return Check(f"model {wanted}", NA, "Ollama not reachable")
    present = wanted in models or f"{wanted}:latest" in models or any(n.startswith(f"{wanted}:") for n in models)
    if present:
        return Check(f"model {wanted}", PASS, "available in Ollama")
    return Check(f"model {wanted}", WARN, "not pulled", f"run `ollama pull {wanted}`")


def _output_dir_check() -> Check:
    target = Path.cwd() / ".modelswapbench"
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("output directory", PASS, f"writable: {target}")
    except OSError as exc:
        return Check("output directory", FAIL, f"not writable: {exc}", "choose a writable --output directory")


def _schema_check() -> Check:
    try:
        schema = benchmark_json_schema()
        return Check("benchmark schema", PASS, f"available ({len(schema.get('properties', {}))} top-level keys)")
    except Exception as exc:  # noqa: BLE001
        return Check("benchmark schema", FAIL, f"unavailable: {exc}")


def _optional_providers_check() -> Check:
    found = [name for name in ("openai", "anthropic", "boto3") if _module_available(name)]
    if found:
        return Check("optional providers", PASS, f"installed extras: {', '.join(found)}")
    return Check("optional providers", NA, "no hosted-provider extras installed (not required for v0.1)")


def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def _env_check() -> Check:
    present = [k for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID") if os.environ.get(k)]
    # Report presence only — never the values.
    if present:
        return Check("provider credentials", PASS, f"detected (names only): {', '.join(present)}")
    return Check("provider credentials", NA, "no hosted-provider credentials set (fine for local-first use)")


def run_checks(base_url: str = DEFAULT_BASE_URL) -> list[Check]:
    """Run all diagnostics and return their results."""
    ollama_check, models = _ollama_check(base_url)
    reachable = ollama_check.status == PASS
    return [
        Check("package version", PASS, f"modelswapbench {__version__}"),
        _python_check(),
        _forge_check(),
        ollama_check,
        _model_check(models, reachable),
        _output_dir_check(),
        _schema_check(),
        _optional_providers_check(),
        _env_check(),
        Check("hosted providers", PASS, "disabled by default (data stays local unless you pass --allow-hosted)"),
    ]
