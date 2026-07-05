"""Cost estimation and the primary economic metric: cost per successful outcome.

Two cost modes are supported:

- ``zero_marginal``    — cost = token count x configured per-million prices (0 for
  local models with no prices). Useful for pure API/token comparison.
- ``estimated_compute`` — additionally attributes local-compute cost (electricity,
  GPU amortization, cloud-GPU-equivalent) from an operator-supplied profile.

All compute figures are clearly labeled estimates; ModelSwapBench never presents
them as measured fact.
"""

from __future__ import annotations

from model_swap_bench.config.models import CostMode, ModelCandidate, ScoringConfig

_MS_PER_HOUR = 3_600_000.0


def token_cost(candidate: ModelCandidate, input_tokens: int, output_tokens: int) -> float:
    """Token-based marginal cost in USD from the candidate's per-million prices."""
    return (
        (input_tokens / 1_000_000.0) * candidate.estimated_input_cost_per_million
        + (output_tokens / 1_000_000.0) * candidate.estimated_output_cost_per_million
    )


def compute_cost(scoring: ScoringConfig, latency_ms: float) -> float:
    """Estimated local-compute cost for one call, or 0 when not in compute mode."""
    if scoring.cost_mode is not CostMode.ESTIMATED_COMPUTE or scoring.compute_profile is None:
        return 0.0
    profile = scoring.compute_profile
    hours = latency_ms / _MS_PER_HOUR
    energy_kwh = (profile.watts / 1000.0) * hours
    energy_cost = energy_kwh * profile.electricity_price_per_kwh
    amort_cost = profile.hardware_amortization_per_hour * hours
    gpu_cost = profile.cloud_gpu_hourly_rate * hours
    return energy_cost + amort_cost + gpu_cost


def estimate_call_cost(
    candidate: ModelCandidate,
    scoring: ScoringConfig,
    *,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
) -> float:
    """Total estimated cost for one model call under the active cost mode."""
    return token_cost(candidate, input_tokens, output_tokens) + compute_cost(scoring, latency_ms)


def cost_per_success(total_cost_usd: float, successful_cases: int) -> float | None:
    """Primary economic metric. Returns ``None`` when there are no successes (undefined)."""
    if successful_cases <= 0:
        return None
    return total_cost_usd / successful_cases
