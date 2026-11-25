"""Writing ``model-swap-evidence.v1``: one tested replacement, as evidence.

The AI Infrastructure Suite scores whether a system could leave its model
provider. A benchmark run that compared the provider's model with an
alternative is evidence for that, and this module writes it as a small,
versioned document the suite can read without importing this package.

One document describes one baseline and one candidate from one stored run. It
carries the numbers a reader needs to recompute the decision for itself, and
this package's own verdict so a reader can refuse a document whose verdict
disagrees with its numbers.

What the document deliberately leaves out:

- every prompt, output, error text and case id;
- full endpoint URLs. Only the origin (scheme, host, port) is written, and a
  URL with credentials, a query string or a fragment never reaches here because
  the suite refuses it on load;
- cost. A more expensive alternative still shows the workload can move, so the
  reader ignores cost and this document does not offer it.

Everything in the document is this tool's own report of what it measured. A
reader can check the arithmetic; it cannot check that any model was run.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic import ValidationError as PydanticValidationError

from model_swap_bench._version import __version__
from model_swap_bench.config.models import BenchmarkSuite, DeploymentType, ModelCandidate, ProviderKind
from model_swap_bench.endpoints import endpoint_is_local
from model_swap_bench.errors import ConfigError
from model_swap_bench.results import BenchmarkRun, ModelSummary
from model_swap_bench.scoring.replacement import (
    FIRST_STAGE_WITH_ESCALATION,
    INSUFFICIENT_EVIDENCE,
    NOT_RECOMMENDED,
    RECOMMENDED,
    RECOMMENDED_WITH_CONDITIONS,
)

SCHEMA_VERSION: Final = "model-swap-evidence.v1"
SCHEMA_ID: Final = "https://github.com/sekacorn/ModelSwapBench/schemas/model-swap-evidence.v1.json"
MAX_TEXT_CHARS: Final = 256
MAX_CONSTRAINTS: Final = 16

#: The endpoint these providers use when a candidate gives no ``base_url``.
_DEFAULT_LOCAL_ORIGIN: Final = "http://localhost:11434"
_PROVIDERS_WITH_A_LOCAL_DEFAULT: Final = frozenset({ProviderKind.OLLAMA, ProviderKind.FORGE})

#: Scheme, host and optional port. The same pattern the suite applies to a
#: provider inventory, so an origin written here matches one written there.
ORIGIN_PATTERN: Final = r"^https?://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(:[0-9]{1,5})?$"
_ORIGIN = re.compile(ORIGIN_PATTERN)

_Text = Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_CHARS)]
_Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Origin = Annotated[str, StringConstraints(max_length=MAX_TEXT_CHARS, pattern=ORIGIN_PATTERN)]
_Count = Annotated[int, Field(ge=0)]
_Rate = Annotated[float, Field(ge=0.0, le=1.0)]
_NonNegative = Annotated[float, Field(ge=0.0)]


class _Closed(BaseModel):
    # hide_input_in_errors: a refused value is never copied into an exception.
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True, allow_inf_nan=False)


class GeneratedBy(_Closed):
    """The producer. A reader treats this as a label, not as proof."""

    tool: Literal["modelswapbench"]
    version: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class RunBinding(_Closed):
    """Which stored run the numbers came from."""

    run_id: _Text
    manifest_hash: _Sha256
    created_at: datetime
    mode: _Text
    suite_name: _Text
    suite_version: _Text


class SummaryNumbers(_Closed):
    """The raw counts and rates for one model. Cases not counted here were skipped."""

    sample_count: _Count
    success_count: _Count
    failure_count: _Count
    error_count: _Count
    timeout_count: _Count
    #: ``None`` when no case executed, so there is no quality to report.
    quality_score: _Rate | None
    #: ``None`` when no case exercised tool selection. Never read as a pass.
    tool_accuracy: _Rate | None
    #: ``None`` when no policy evidence was collected. Never read as a pass.
    policy_pass_rate: _Rate | None
    p95_latency_ms: _NonNegative
    evidence_sufficient: bool
    minimum_recommended_sample_size: Annotated[int, Field(ge=1)]


class ModelSide(_Closed):
    """One side of the comparison: where it runs and what it scored."""

    alias: _Text
    provider_kind: ProviderKind
    model: _Text
    #: ``None`` when the provider has no endpoint of its own to state: the
    #: deterministic provider, or a vendor SDK using its built-in default.
    endpoint_origin: _Origin | None
    deployment_declared: DeploymentType
    summary: SummaryNumbers


class Thresholds(_Closed):
    """The limits the run was judged against."""

    maximum_quality_drop: _NonNegative
    minimum_reliability: _Rate | None
    maximum_latency_ms: _NonNegative | None
    #: Recorded for completeness. A reader scoring portability ignores cost.
    minimum_cost_reduction: float
    hosted_candidates_permitted: bool


class ConstraintOutcome(_Closed):
    """One suite-level constraint checked against the candidate."""

    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,64}$")]
    passed: bool


class Verdict(_Closed):
    """This package's own decision, for a reader to check against the numbers."""

    recommendation: Literal[
        "recommended replacement",
        "recommended with conditions",
        "suitable as first-stage model with escalation",
        "not recommended",
        "insufficient evidence",
    ]
    eligible: bool
    policy_pass: bool
    deployment_compatible: bool


class ModelSwapEvidence(_Closed):
    """A ``model-swap-evidence.v1`` document."""

    schema_version: Literal["model-swap-evidence.v1"]
    generated_by: GeneratedBy
    run: RunBinding
    baseline: ModelSide
    candidate: ModelSide
    thresholds: Thresholds
    candidate_constraints: Annotated[list[ConstraintOutcome], Field(max_length=MAX_CONSTRAINTS)]
    verdict: Verdict


_RECOMMENDATIONS: Final = frozenset(
    {RECOMMENDED, RECOMMENDED_WITH_CONDITIONS, FIRST_STAGE_WITH_ESCALATION, NOT_RECOMMENDED, INSUFFICIENT_EVIDENCE}
)


def endpoint_origin(base_url: str) -> str:
    """Reduce a configured ``base_url`` to ``scheme://host[:port]``, lower-cased.

    The error never repeats the URL: an endpoint field is exactly where a
    misplaced credential would be.
    """
    try:
        parts = urlsplit(base_url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        raise ConfigError("a model's base_url cannot be reduced to an origin.") from None
    scheme = parts.scheme.lower()
    if ":" in host:
        host = f"[{host}]"
    origin = f"{scheme}://{host}" + (f":{port}" if port is not None else "")
    if parts.username is not None or parts.password is not None or not _ORIGIN.fullmatch(origin):
        raise ConfigError("a model's base_url cannot be reduced to an origin.")
    return origin


def _origin_for(candidate: ModelCandidate) -> str | None:
    if candidate.base_url:
        return endpoint_origin(candidate.base_url)
    if candidate.provider in _PROVIDERS_WITH_A_LOCAL_DEFAULT:
        return _DEFAULT_LOCAL_ORIGIN
    return None


def _numbers(summary: ModelSummary) -> dict[str, Any]:
    executed = summary.successful_cases + summary.failed_cases
    return {
        "sample_count": summary.total_cases,
        "success_count": summary.successful_cases,
        "failure_count": summary.failed_cases,
        "error_count": summary.error_cases,
        "timeout_count": summary.timeout_cases,
        "quality_score": summary.quality_score if executed else None,
        "tool_accuracy": summary.tool_accuracy,
        "policy_pass_rate": summary.policy_pass_rate,
        "p95_latency_ms": summary.p95_latency_ms,
        "evidence_sufficient": summary.evidence_sufficient,
        "minimum_recommended_sample_size": summary.minimum_recommended_sample_size,
    }


def _refuse_local_at_a_host_that_is_not_local(candidate: ModelCandidate, origin: str | None, role: str) -> None:
    """Refuse what the AI Infrastructure Suite refuses, so this writer is never wider.

    A model declared ``local`` whose endpoint is not local (a public host, an
    unresolved name, or a hosted SDK default) would send content off the
    machine while the document said it stayed. The suite's reader refuses such
    a document, and so does the provider inventory. Declare ``self_hosted`` or
    ``hosted`` instead. Deterministic fixtures have no endpoint and are exempt.
    """
    if candidate.deployment is not DeploymentType.LOCAL or candidate.provider is ProviderKind.DETERMINISTIC:
        return
    if origin is None or not endpoint_is_local(origin):
        raise ConfigError(
            f"the {role} model is declared local but its endpoint is not local; "
            "declare deployment: self_hosted or hosted to write swap evidence."
        )


def _side(candidate: ModelCandidate, summary: ModelSummary) -> dict[str, Any]:
    return {
        "alias": candidate.alias,
        "provider_kind": candidate.provider,
        "model": candidate.model,
        "endpoint_origin": _origin_for(candidate),
        "deployment_declared": candidate.deployment,
        "summary": _numbers(summary),
    }


def build_swap_evidence(run: BenchmarkRun, suite: BenchmarkSuite, candidate_alias: str) -> ModelSwapEvidence:
    """Build the evidence document for one candidate of a stored run.

    ``suite`` is the snapshot stored with the run, which is what the run's
    manifest hash commits to.
    """
    config = suite.replacement
    if config is None:
        raise ConfigError("this run has no replacement section, so it compared nothing against a baseline.")
    decision = next((d for d in run.replacement_decisions if d.candidate_model == candidate_alias), None)
    if decision is None or decision.baseline_model != config.baseline:
        raise ConfigError("no replacement decision is stored for that candidate; choose one of the run's replacement candidates.")
    if decision.recommendation not in _RECOMMENDATIONS:
        raise ConfigError("the stored replacement decision has a recommendation this version does not know.")
    if not re.fullmatch(r"[0-9a-f]{64}", run.manifest_hash):
        raise ConfigError("the run has no manifest hash; evidence can only be written for a stored run.")

    sides: dict[str, dict[str, Any]] = {}
    for role, alias in (("baseline", config.baseline), ("candidate", candidate_alias)):
        model = next((m for m in suite.models if m.alias == alias), None)
        summary = run.summary_for(alias)
        if model is None or summary is None:
            raise ConfigError(f"the run has no results for its {role} model.")
        _refuse_local_at_a_host_that_is_not_local(model, _origin_for(model), role)
        sides[role] = _side(model, summary)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_by": {"tool": "modelswapbench", "version": __version__},
        "run": {
            "run_id": run.run_id,
            "manifest_hash": run.manifest_hash,
            "created_at": run.created_at.astimezone(UTC),
            "mode": run.mode,
            "suite_name": run.suite_name,
            "suite_version": run.suite_version,
        },
        "baseline": sides["baseline"],
        "candidate": sides["candidate"],
        "thresholds": {
            "maximum_quality_drop": config.maximum_quality_drop,
            "minimum_reliability": config.minimum_reliability,
            "maximum_latency_ms": config.maximum_latency_ms,
            "minimum_cost_reduction": config.minimum_cost_reduction,
            "hosted_candidates_permitted": suite.privacy.allow_hosted_providers,
        },
        "candidate_constraints": [
            {"name": c.name, "passed": c.passed} for c in sorted(run.constraint_results.get(candidate_alias, []), key=lambda c: c.name)
        ],
        "verdict": {
            "recommendation": decision.recommendation,
            "eligible": decision.eligible,
            "policy_pass": decision.policy_pass,
            "deployment_compatible": decision.deployment_compatible,
        },
    }
    try:
        return ModelSwapEvidence.model_validate(payload)
    except PydanticValidationError as exc:
        # Field paths and reasons only: hide_input_in_errors keeps values out.
        where = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
        raise ConfigError(f"this run cannot be written as {SCHEMA_VERSION}: out of bounds at {', '.join(where)}.") from None


def render_swap_evidence_json(evidence: ModelSwapEvidence) -> str:
    """Serialize deterministically: sorted keys, UTC timestamp, no NaN."""
    return json.dumps(evidence.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def swap_evidence_json_schema() -> dict[str, Any]:
    """The JSON Schema for what this module writes, derived from the models."""
    schema = ModelSwapEvidence.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": SCHEMA_VERSION,
        **{key: value for key, value in schema.items() if key != "title"},
    }


def swap_evidence_schema_json() -> str:
    return json.dumps(swap_evidence_json_schema(), indent=2, sort_keys=False) + "\n"
