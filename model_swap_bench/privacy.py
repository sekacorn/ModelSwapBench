"""Explicit provider and dataset data-safety preflight."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DataSafetyPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    hosting_mode: str
    is_hosted: bool
    dataset_privacy_classification: str
    raw_prompts_transmitted: bool
    raw_outputs_stored: bool
    telemetry_enabled: bool
    hosted_execution_confirmed: bool
    redaction_applied: bool
    content_leaves_machine: bool
    allowed: bool
    warnings: list[str] = Field(default_factory=list)


def provider_data_preflight(
    *,
    provider: str,
    hosting_mode: str,
    dataset_privacy_classification: str,
    allow_hosted: bool,
    raw_outputs_stored: bool,
    telemetry_enabled: bool = False,
    redaction_applied: bool = False,
) -> DataSafetyPreflight:
    is_hosted = hosting_mode.lower() == "hosted"
    content_leaves = is_hosted and allow_hosted
    warnings: list[str] = []
    allowed = not is_hosted or allow_hosted
    if is_hosted and not allow_hosted:
        warnings.append("hosted execution is blocked until explicitly enabled")
    if is_hosted and dataset_privacy_classification not in {"public", "unknown"} and not redaction_applied:
        warnings.append("private unredacted dataset content would be transmitted to a hosted provider")
    if telemetry_enabled:
        warnings.append("telemetry is enabled; review exported fields before execution")
    return DataSafetyPreflight(
        provider=provider,
        hosting_mode=hosting_mode,
        is_hosted=is_hosted,
        dataset_privacy_classification=dataset_privacy_classification,
        raw_prompts_transmitted=content_leaves,
        raw_outputs_stored=raw_outputs_stored,
        telemetry_enabled=telemetry_enabled,
        hosted_execution_confirmed=allow_hosted,
        redaction_applied=redaction_applied,
        content_leaves_machine=content_leaves,
        allowed=allowed,
        warnings=warnings,
    )
