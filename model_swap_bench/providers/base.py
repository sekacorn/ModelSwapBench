"""Provider abstraction.

Every model backend implements :class:`Provider`. Requests and responses are
plain, provider-neutral value objects so adapters can be swapped freely — a core
anti-lock-in guarantee of ModelSwapBench.
"""

from __future__ import annotations

import abc
from pathlib import Path

from pydantic import BaseModel, Field

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.results import ToolCallRecord


class ProviderRequest(BaseModel):
    """A single, provider-neutral model call."""

    model_id: str
    prompt: str
    system: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    max_tokens: int = 1024
    timeout_seconds: float = 60.0
    available_tools: list[str] = Field(default_factory=list)
    # Case context — used only by the deterministic test provider (never sent to
    # a real model). Real providers ignore these.
    case_id: str | None = None
    expected: dict[str, object] | None = None
    expected_text: str | None = None


class ProviderResponse(BaseModel):
    """A single, provider-neutral model response."""

    text: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    reported_model: str | None = None
    execution_path: str = "direct"
    endpoint: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    """Result of a provider health/availability check."""

    available: bool
    detail: str = ""
    endpoint: str | None = None
    hosted: bool = False


class Provider(abc.ABC):
    """Abstract base class for all model providers."""

    kind: ProviderKind

    def __init__(self, candidate: ModelCandidate) -> None:
        self.candidate = candidate

    @property
    def alias(self) -> str:
        return self.candidate.alias

    @abc.abstractmethod
    async def health(self) -> HealthStatus:
        """Return whether this provider (and its model) is usable, without side effects."""

    @abc.abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Execute one model call."""

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        """Release any resources (HTTP clients, pools). Safe to call more than once."""
        return None


def build_provider(
    candidate: ModelCandidate,
    *,
    suite_dir: Path | None = None,
    allow_hosted: bool = False,
) -> Provider:
    """Instantiate the right :class:`Provider` for a model candidate.

    Hosted providers are refused unless ``allow_hosted`` is true; this is the
    load-bearing privacy guard that keeps benchmark data local by default.
    """
    # Imported lazily to avoid import cycles between provider modules.
    from model_swap_bench.providers.deterministic import DeterministicProvider
    from model_swap_bench.providers.forge import ForgeProviderAdapter
    from model_swap_bench.providers.ollama import OllamaProvider
    from model_swap_bench.providers.openai_compatible import OpenAICompatibleProvider

    kind = candidate.provider
    if kind is ProviderKind.DETERMINISTIC:
        return DeterministicProvider(candidate, suite_dir=suite_dir)
    if kind is ProviderKind.OLLAMA:
        return OllamaProvider(candidate)
    if kind is ProviderKind.FORGE:
        return ForgeProviderAdapter(candidate)
    if kind is ProviderKind.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(candidate, allow_hosted=allow_hosted)

    from model_swap_bench.errors import ProviderUnavailableError

    if candidate.is_hosted and not allow_hosted:
        raise ProviderUnavailableError(
            f"Provider {kind.value!r} for model {candidate.alias!r} is a hosted provider and is disabled. "
            "Enable it explicitly with privacy.allow_hosted_providers and --allow-hosted."
        )
    raise ProviderUnavailableError(
        f"Provider {kind.value!r} is not implemented in v0.1. "
        "Deterministic, Ollama, Forge, and OpenAI-compatible providers are supported."
    )
