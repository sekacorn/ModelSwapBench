"""Forge (agentforge-oss) provider adapter.

Routes model calls through the real ``agentforge-oss`` provider API rather than
our own HTTP client, so results reflect the Forge execution path. The adapter
uses Forge's own ``OllamaProvider`` and records ``execution_path='forge->ollama'``
so reports never misattribute a direct call as a Forge call.

Limitation (documented for v0.1): this adapter exercises Forge's provider layer,
not full Forge orchestration (agents/tools/memory). Orchestrated execution is on
the roadmap; see docs/providers.md.
"""

from __future__ import annotations

from typing import Any

import httpx

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.errors import ProviderResponseError, ProviderUnavailableError
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse
from model_swap_bench.results import ToolCallRecord

DEFAULT_BASE_URL = "http://localhost:11434"


class ForgeProviderAdapter(Provider):
    """Execute model calls through the agentforge-oss provider API."""

    kind = ProviderKind.FORGE

    def __init__(self, candidate: ModelCandidate) -> None:
        super().__init__(candidate)
        self._base_url = (candidate.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = candidate.timeout_seconds or 120.0
        self._provider: Any | None = None

    def _get_provider(self) -> Any:
        if self._provider is None:
            try:
                from forge import OllamaProvider as ForgeOllama
            except ImportError as exc:  # pragma: no cover - forge is a hard dependency
                raise ProviderUnavailableError("agentforge-oss is not installed; install modelswapbench with its dependencies") from exc
            self._provider = ForgeOllama(self._base_url, timeout=self._timeout)
        return self._provider

    async def health(self) -> HealthStatus:
        # Forge executes against Ollama; probe the same endpoint without side effects.
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            return HealthStatus(
                available=False,
                detail=f"Forge target Ollama unreachable at {self._base_url}: {exc}",
                endpoint=self._base_url,
            )
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        wanted = self.candidate.model
        has_model = wanted in names or f"{wanted}:latest" in names or any(n.startswith(f"{wanted}:") for n in names)
        detail = f"Forge->Ollama reachable; {wanted} {'present' if has_model else 'MISSING'}"
        return HealthStatus(available=has_model, detail=detail, endpoint=self._base_url)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        from forge import Message

        provider = self._get_provider()
        messages = [Message(role="user", content=request.prompt)]  # type: ignore[arg-type]
        try:
            response = await provider.complete(
                messages,
                model=request.model_id,
                system=request.system,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise ProviderResponseError(f"Forge provider call failed: {exc}") from exc

        content = getattr(response, "content", None)
        if not isinstance(content, str):
            raise ProviderResponseError("Forge response missing text content")
        usage = getattr(response, "usage", None)
        tool_calls = [
            ToolCallRecord(
                name=str(getattr(tc, "name", "")),
                arguments=dict(getattr(tc, "arguments", {}) or {}),
            )
            for tc in (getattr(response, "tool_calls", None) or [])
        ]
        return ProviderResponse(
            text=content,
            tool_calls=tool_calls,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            reported_model=str(getattr(response, "model", request.model_id)),
            execution_path="forge->ollama",
            endpoint=self._base_url,
            raw={"finish_reason": str(getattr(response, "finish_reason", ""))},
        )

    async def aclose(self) -> None:
        if self._provider is not None:
            aclose = getattr(self._provider, "aclose", None)
            if aclose is not None:
                await aclose()
            self._provider = None
