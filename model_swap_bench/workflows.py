"""Portable multi-turn and tool-workflow evidence."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StepKind(str, Enum):
    USER_MESSAGE = "user_message"
    MODEL_RESPONSE = "model_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    HUMAN_REVIEW = "human_review"
    FINAL_ANSWER = "final_answer"


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    sequence: int = Field(ge=0)
    kind: StepKind
    content: str | None = Field(default=None, max_length=65_536)
    tool_name: str | None = Field(default=None, max_length=256)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_succeeded: bool | None = None
    latency_ms: float = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    error_type: str | None = Field(default=None, max_length=256)
    timeout: bool = False
    policy_result: str | None = Field(default=None, max_length=256)


class WorkflowTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    trace_id: str = Field(min_length=1, max_length=256)
    case_id: str = Field(min_length=1, max_length=256)
    task_id: str | None = Field(default=None, max_length=256)
    requested_model: str = Field(min_length=1, max_length=512)
    response_model: str | None = Field(default=None, max_length=512)
    provider: str = Field(min_length=1, max_length=256)
    expected_tool_sequence: list[str] = Field(default_factory=list, max_length=100)
    steps: list[WorkflowStep] = Field(min_length=1, max_length=500)
    business_success: bool | None = None
    human_outcome: str | None = Field(default=None, max_length=256)
    risk_level: str = Field(default="unknown", max_length=64)
    privacy_classification: str = Field(default="unknown", max_length=64)

    @model_validator(mode="after")
    def _ordered_steps(self) -> WorkflowTrace:
        sequences = [step.sequence for step in self.steps]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("workflow steps must have unique ascending sequence numbers")
        return self


class WorkflowEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: str
    step_count: int
    tool_call_count: int
    tool_selection_accuracy: float | None
    tool_order_correct: bool | None
    unnecessary_tool_calls: int
    tool_failures: int
    recovered_tool_failures: int
    timeouts: int
    timeout_recovered: bool
    loop_detected: bool
    step_limit_exceeded: bool
    policy_pass: bool | None
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_usd: Decimal | None
    end_to_end_latency_ms: float
    escalated: bool
    human_reviewed: bool
    business_success: bool | None
    warnings: list[str] = Field(default_factory=list)


def evaluate_workflow(trace: WorkflowTrace, *, step_limit: int = 100) -> WorkflowEvaluation:
    tool_steps = [step for step in trace.steps if step.kind is StepKind.TOOL_CALL]
    actual_tools = [step.tool_name or "" for step in tool_steps]
    expected_tools = trace.expected_tool_sequence
    matches = sum(actual == expected for actual, expected in zip(actual_tools, expected_tools, strict=False))
    accuracy = None if not expected_tools else round(matches / max(len(expected_tools), len(actual_tools), 1), 4)
    signatures = [(step.kind.value, step.tool_name, step.content) for step in trace.steps]
    loop_detected = any(signatures.count(signature) >= 3 for signature in set(signatures))
    failed_indexes = [index for index, step in enumerate(trace.steps) if step.kind is StepKind.TOOL_RESULT and step.tool_succeeded is False]
    recovered = sum(
        any(later.kind in {StepKind.MODEL_RESPONSE, StepKind.FINAL_ANSWER} and not later.error_type for later in trace.steps[index + 1 :])
        for index in failed_indexes
    )
    known_costs = [step.estimated_cost_usd for step in trace.steps if step.estimated_cost_usd is not None]
    cost = sum(known_costs, Decimal("0")) if len(known_costs) == len(trace.steps) else None
    policy_values = [step.policy_result for step in trace.steps if step.policy_result is not None]
    policy_pass = None if not policy_values else all(value.lower() in {"pass", "allowed"} for value in policy_values)
    timeout_indexes = [index for index, step in enumerate(trace.steps) if step.timeout]
    timeout_recovered = bool(timeout_indexes) and any(
        later.kind is StepKind.FINAL_ANSWER and not later.error_type for index in timeout_indexes for later in trace.steps[index + 1 :]
    )
    warnings: list[str] = []
    if cost is None:
        warnings.append("total workflow cost is unknown because one or more step costs are missing")
    if loop_detected:
        warnings.append("repeated workflow steps indicate a possible loop")
    if len(trace.steps) > step_limit:
        warnings.append(f"workflow exceeded the configured {step_limit}-step limit")
    return WorkflowEvaluation(
        trace_id=trace.trace_id,
        step_count=len(trace.steps),
        tool_call_count=len(tool_steps),
        tool_selection_accuracy=accuracy,
        tool_order_correct=None if not expected_tools else actual_tools == expected_tools,
        unnecessary_tool_calls=max(0, len(actual_tools) - len(expected_tools)),
        tool_failures=len(failed_indexes),
        recovered_tool_failures=recovered,
        timeouts=len(timeout_indexes),
        timeout_recovered=timeout_recovered,
        loop_detected=loop_detected,
        step_limit_exceeded=len(trace.steps) > step_limit,
        policy_pass=policy_pass,
        total_input_tokens=sum(step.input_tokens for step in trace.steps),
        total_output_tokens=sum(step.output_tokens for step in trace.steps),
        total_estimated_cost_usd=cost,
        end_to_end_latency_ms=round(sum(step.latency_ms for step in trace.steps), 3),
        escalated=any(step.kind is StepKind.HUMAN_REVIEW for step in trace.steps),
        human_reviewed=any(step.kind is StepKind.HUMAN_REVIEW for step in trace.steps),
        business_success=trace.business_success,
        warnings=warnings,
    )
