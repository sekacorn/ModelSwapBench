"""Every variant of ``model-swap-evidence.v1`` this package can emit.

Built through the real decision engine and the real writer, from fixed numbers,
so each committed fixture is exactly what the code produces. The unit tests
compare the two, and the cross-repo contract test feeds every variant to the
AI Infrastructure Suite's reader.

Hosts and names are placeholders: ``*.example``, ``vendor_a``, ``model-large``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from model_swap_bench.config import build_suite
from model_swap_bench.config.models import BenchmarkSuite
from model_swap_bench.reports.swap_evidence import ModelSwapEvidence, build_swap_evidence
from model_swap_bench.results import BenchmarkRun, ConstraintResult, ModelSummary
from model_swap_bench.scoring.replacement import decide_replacement

FIXTURE_DIR: Final = Path(__file__).resolve().parent.parent / "fixtures" / "model-swap-evidence"
CREATED_AT: Final = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)

_BASELINE: Final[dict[str, Any]] = {
    "alias": "current",
    "provider": "openai_compatible",
    "model": "model-large",
    "deployment": "hosted",
    "base_url": "https://llm.vendor-a.example/v1",
    "api_key_env": "VENDOR_A_API_KEY",
}
_LOCAL: Final[dict[str, Any]] = {
    "alias": "local_alt",
    "provider": "ollama",
    "model": "model-small",
    "deployment": "local",
    "base_url": "http://127.0.0.1:11434",
}
_HOSTED: Final[dict[str, Any]] = {
    "alias": "other_vendor",
    "provider": "openai_compatible",
    "model": "model-medium",
    "deployment": "hosted",
    "base_url": "https://API.vendor-b.example:8443/v1",
    "api_key_env": "VENDOR_B_API_KEY",
}
_SELF_HOSTED_V6: Final[dict[str, Any]] = {
    "alias": "rack_alt",
    "provider": "openai_compatible",
    "model": "model-small",
    "deployment": "self_hosted",
    "base_url": "http://[fd00::10]:8000/v1",
}
_DEFAULT_ENDPOINT: Final[dict[str, Any]] = {"alias": "default_alt", "provider": "ollama", "model": "model-small", "deployment": "local"}
_FAKE: Final[dict[str, Any]] = {"alias": "fake_alt", "provider": "deterministic", "model": "fixture", "deployment": "test"}


def _summary(alias: str, model: dict[str, Any], **numbers: Any) -> ModelSummary:
    total = numbers.pop("total", 24)
    success = numbers.pop("success", total)
    failed = numbers.pop("failed", 0)
    errors = numbers.pop("errors", 0)
    timeouts = numbers.pop("timeouts", 0)
    return ModelSummary(
        model_alias=alias,
        provider=model["provider"],
        deployment=model["deployment"],
        total_cases=total,
        successful_cases=success,
        failed_cases=failed,
        error_cases=errors,
        timeout_cases=timeouts,
        success_rate=success / total if total else 0.0,
        evidence_sufficient=total >= 20,
        **numbers,
    )


def _variant(
    name: str,
    candidate_model: dict[str, Any],
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    replacement: dict[str, Any] | None = None,
    constraints: list[ConstraintResult] | None = None,
) -> tuple[BenchmarkRun, BenchmarkSuite, str]:
    alias = candidate_model["alias"]
    suite = build_suite(
        {
            "name": f"swap-{name}",
            "version": "1.0",
            "baseline_model": "current",
            "models": [_BASELINE, candidate_model],
            "cases": [{"id": "c1", "input": {"message": "hi"}, "expected": {"category": "billing"}}],
            "evaluators": ["json_parse", "field_match"],
            "privacy": {"allow_hosted_providers": True},
            "replacement": {"baseline": "current", "candidates": [alias], **(replacement or {})},
        }
    )
    assert suite.replacement is not None
    baseline_summary = _summary("current", _BASELINE, **baseline)
    candidate_summary = _summary(alias, candidate_model, **candidate)
    checked = constraints or []
    decision = decide_replacement(
        baseline_summary,
        candidate_summary,
        suite.models[1],
        suite.replacement,
        candidate_constraints=checked,
        privacy_allows_hosted=suite.privacy.allow_hosted_providers,
    )
    run = BenchmarkRun(
        run_id=f"run-{name}",
        suite_name=suite.name,
        suite_version=suite.version,
        mode="compare",
        created_at=CREATED_AT,
        baseline_model="current",
        model_summaries=[baseline_summary, candidate_summary],
        constraint_results={alias: checked},
        replacement_decisions=[decision],
        manifest_hash=hashlib.sha256(name.encode()).hexdigest(),
    )
    return run, suite, alias


def _inputs() -> dict[str, tuple[BenchmarkRun, BenchmarkSuite, str]]:
    good = {"quality_score": 0.92, "p95_latency_ms": 840.0}
    return {
        # A local alternative that held quality: the case that can score best.
        "local-accepted": _variant(
            "local-accepted", _LOCAL, baseline=good, candidate={"quality_score": 0.9, "p95_latency_ms": 1210.5, "success": 23, "failed": 1}
        ),
        # Accepted, but the alternative is another vendor.
        "hosted-accepted": _variant("hosted-accepted", _HOSTED, baseline=good, candidate={"quality_score": 0.93, "p95_latency_ms": 610.0}),
        # A private IPv6 endpoint, declared self-hosted.
        "self-hosted-ipv6": _variant(
            "self-hosted-ipv6", _SELF_HOSTED_V6, baseline=good, candidate={"quality_score": 0.91, "p95_latency_ms": 990.0}
        ),
        # No base_url: the provider's own local default is written.
        "default-endpoint": _variant(
            "default-endpoint", _DEFAULT_ENDPOINT, baseline=good, candidate={"quality_score": 0.9, "p95_latency_ms": 1500.0}
        ),
        # Tool selection and policy were both exercised and passed.
        "tools-and-policy": _variant(
            "tools-and-policy",
            _LOCAL,
            baseline={**good, "tool_accuracy": 1.0, "policy_pass_rate": 1.0},
            candidate={"quality_score": 0.9, "p95_latency_ms": 1100.0, "tool_accuracy": 0.9583, "policy_pass_rate": 1.0},
            replacement={"minimum_reliability": 0.9, "maximum_latency_ms": 2000.0},
            constraints=[
                ConstraintResult(name="require_policy_pass", passed=True, threshold=True, actual=1.0),
                ConstraintResult(name="minimum_tool_accuracy", passed=True, threshold=0.9, actual=0.9583),
            ],
        ),
        # Too few cases to decide anything.
        "insufficient-samples": _variant(
            "insufficient-samples",
            _LOCAL,
            baseline={**good, "total": 5},
            candidate={"quality_score": 0.9, "p95_latency_ms": 1000.0, "total": 5},
        ),
        # Quality fell too far and a constraint failed.
        "not-recommended": _variant(
            "not-recommended",
            _LOCAL,
            baseline=good,
            candidate={"quality_score": 0.61, "p95_latency_ms": 1300.0, "success": 15, "failed": 7, "errors": 1, "timeouts": 1},
            constraints=[ConstraintResult(name="minimum_success_rate", passed=False, threshold=0.8, actual=0.625)],
        ),
        # A measured policy violation.
        "policy-failed": _variant(
            "policy-failed", _LOCAL, baseline=good, candidate={"quality_score": 0.92, "p95_latency_ms": 900.0, "policy_pass_rate": 0.875}
        ),
        # Nothing executed: every case errored, so there is no quality to report.
        "nothing-executed": _variant(
            "nothing-executed", _LOCAL, baseline=good, candidate={"quality_score": 0.0, "p95_latency_ms": 0.0, "success": 0, "errors": 24}
        ),
        # A deterministic fake candidate. A reader reports it and moves nothing.
        "fake-candidate": _variant("fake-candidate", _FAKE, baseline=good, candidate={"quality_score": 1.0, "p95_latency_ms": 10.0}),
    }


VARIANTS: Final = tuple(_inputs())


def build(name: str) -> ModelSwapEvidence:
    run, suite, alias = _inputs()[name]
    return build_swap_evidence(run, suite, alias)


def build_all() -> dict[str, ModelSwapEvidence]:
    return {name: build(name) for name in VARIANTS}


def run_for(name: str) -> tuple[BenchmarkRun, BenchmarkSuite, str]:
    return _inputs()[name]
