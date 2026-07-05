"""Exception hierarchy and process exit codes for ModelSwapBench.

Exit codes are part of the CLI contract (documented in the README):

- 0 success
- 1 benchmark completed but one or more constraints failed
- 2 invalid configuration or input
- 3 a required provider was unavailable
- 4 partial / degraded run
- 5 internal execution error
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable process exit codes for the ``modelswapbench`` CLI."""

    SUCCESS = 0
    CONSTRAINTS_FAILED = 1
    INVALID_INPUT = 2
    PROVIDER_UNAVAILABLE = 3
    PARTIAL_RUN = 4
    INTERNAL_ERROR = 5


class ModelSwapBenchError(Exception):
    """Base class for all ModelSwapBench errors."""

    exit_code: ExitCode = ExitCode.INTERNAL_ERROR


class ConfigError(ModelSwapBenchError):
    """Invalid benchmark configuration or input file."""

    exit_code = ExitCode.INVALID_INPUT


class ValidationError(ConfigError):
    """A benchmark suite failed semantic validation."""


class ProviderError(ModelSwapBenchError):
    """A model provider failed in a structured, expected way."""


class ProviderUnavailableError(ProviderError):
    """A required provider (endpoint, model, dependency) is not available."""

    exit_code = ExitCode.PROVIDER_UNAVAILABLE


class ProviderTimeoutError(ProviderError):
    """A model call exceeded its configured timeout."""


class ProviderResponseError(ProviderError):
    """A provider returned a malformed or unusable response."""


class StorageError(ModelSwapBenchError):
    """A run repository / storage operation failed."""


class SecurityError(ModelSwapBenchError):
    """A path-traversal, redaction, or other safety guard was triggered."""

    exit_code = ExitCode.INVALID_INPUT
