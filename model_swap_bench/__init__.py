"""ModelSwapBench — open-source model portability and replacement benchmark.

Run the same workflow across local, open-weight, self-hosted, and hosted models
and measure quality, latency, policy compliance, and cost per successful outcome
before committing to a vendor.
"""

from __future__ import annotations

from model_swap_bench._version import __version__
from model_swap_bench.errors import (
    ConfigError,
    ExitCode,
    ModelSwapBenchError,
    ProviderError,
    ProviderUnavailableError,
    ValidationError,
)

__all__ = [
    "__version__",
    "ConfigError",
    "ExitCode",
    "ModelSwapBenchError",
    "ProviderError",
    "ProviderUnavailableError",
    "ValidationError",
]
