"""Deterministic OpenTelemetry-compatible JSON mappings without an SDK dependency."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from model_swap_bench._version import __version__
from model_swap_bench.portable import canonical_json
from model_swap_bench.workflows import WorkflowTrace, evaluate_workflow

MAPPING_VERSION = "modelswapbench.otel.v1"
SCHEMA_URL = "https://opentelemetry.io/schemas/1.30.0"


class OTelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_type: str = "opentelemetry-compatible-genai-record"
    schema_version: str = "modelswapbench.telemetry.v1"
    modelswapbench_version: str = __version__
    mapping_version: str = MAPPING_VERSION
    schema_url: str = SCHEMA_URL
    run_id: str
    dataset_digest: str
    reproducibility_metadata: dict[str, Any]
    operation_name: str
    attributes: dict[str, Any]
    unsupported_fields: list[str] = Field(default_factory=list)


def workflow_to_otel(
    trace: WorkflowTrace,
    *,
    dataset_id: str,
    dataset_digest: str,
    benchmark_run_id: str,
    evaluation_score: float | None = None,
    route_decision: str | None = None,
) -> OTelRecord:
    evidence = evaluate_workflow(trace)
    attributes: dict[str, Any] = {
        "gen_ai.operation.name": "workflow.evaluate",
        "gen_ai.provider.name": trace.provider,
        "gen_ai.request.model": trace.requested_model,
        "gen_ai.response.model": trace.response_model,
        "gen_ai.usage.input_tokens": evidence.total_input_tokens,
        "gen_ai.usage.output_tokens": evidence.total_output_tokens,
        "modelswapbench.version": __version__,
        "modelswapbench.dataset.id": dataset_id,
        "modelswapbench.dataset.digest": dataset_digest,
        "modelswapbench.case.id": trace.case_id,
        "modelswapbench.run.id": benchmark_run_id,
        "modelswapbench.trace.id": trace.trace_id,
        "modelswapbench.latency_ms": evidence.end_to_end_latency_ms,
        "modelswapbench.tool_call_count": evidence.tool_call_count,
        "modelswapbench.risk_level": trace.risk_level,
        "modelswapbench.business_success": trace.business_success,
        "modelswapbench.estimated_cost_usd": None if evidence.total_estimated_cost_usd is None else str(evidence.total_estimated_cost_usd),
        "modelswapbench.evaluation_score": evaluation_score,
        "modelswapbench.route_decision": route_decision,
    }
    return OTelRecord(
        run_id=benchmark_run_id,
        dataset_digest=dataset_digest,
        reproducibility_metadata={"dataset_id": dataset_id, "case_id": trace.case_id, "trace_id": trace.trace_id},
        operation_name="workflow.evaluate",
        attributes=attributes,
        unsupported_fields=["trace_state", "span_links", "resource_attributes"],
    )


def render_otel_jsonl(records: list[OTelRecord]) -> str:
    return "\n".join(canonical_json(record.model_dump(mode="json")) for record in records) + ("\n" if records else "")
