"""OpenAI-compatible provider for self-hosted endpoints (vLLM, llama.cpp, LM Studio, gateways).

Disabled unless a ``base_url`` is configured. Endpoints are classified as local or
external; external endpoints require ``--allow-hosted`` because data would leave
the machine. API keys are read from an environment variable (never stored in the
suite) and are never written to results or reports.
"""

from __future__ import annotations

import os

import httpx

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.endpoints import endpoint_is_local, redact_query_values_in_logs
from model_swap_bench.errors import (
    ConfigError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse

__all__ = ["OpenAICompatibleProvider", "endpoint_is_local"]
# endpoint_is_local moved to model_swap_bench.endpoints so the configuration
# layer can use the same rule. Re-exported here because it was importable from
# this module and removing that would break a caller for no gain.


class OpenAICompatibleProvider(Provider):
    """Call a self-hosted OpenAI-compatible ``/v1/chat/completions`` endpoint."""

    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self, candidate: ModelCandidate, *, allow_hosted: bool = False) -> None:
        super().__init__(candidate)
        if not candidate.base_url:
            raise ConfigError(f"model {candidate.alias!r}: openai_compatible provider requires a base_url (e.g. http://localhost:8000/v1)")
        self._base_url = candidate.base_url.rstrip("/")
        self._is_local = endpoint_is_local(self._base_url)
        if not self._is_local and not allow_hosted:
            raise ProviderUnavailableError(
                f"model {candidate.alias!r}: endpoint {self._base_url} is external. "
                "Re-run with --allow-hosted (and privacy.allow_hosted_providers) to permit it."
            )
        self._timeout = candidate.timeout_seconds or 120.0
        self._api_key = os.environ.get(candidate.api_key_env) if candidate.api_key_env else None
        self._default_query = dict(candidate.default_query)
        if self._default_query:
            redact_query_values_in_logs(self._default_query.values())
        self._client: httpx.AsyncClient | None = None

    @property
    def classification(self) -> str:
        return "local" if self._is_local else "external"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=headers,
                params=self._default_query or None,
            )
        return self._client

    async def health(self) -> HealthStatus:
        try:
            resp = await self._get_client().get("/models")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return HealthStatus(
                available=False,
                detail=f"cannot reach OpenAI-compatible endpoint ({self.classification}): {type(exc).__name__}",
                endpoint=self._base_url,
                hosted=not self._is_local,
            )
        return HealthStatus(
            available=True,
            detail=f"endpoint reachable ({self.classification})",
            endpoint=self._base_url,
            hosted=not self._is_local,
        )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        payload = {
            "model": request.model_id,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        try:
            resp = await self._get_client().post("/chat/completions", json=payload, timeout=request.timeout_seconds)
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"endpoint call timed out after {request.timeout_seconds}s") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(f"endpoint returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"endpoint unreachable ({type(exc).__name__})") from None
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError("endpoint response missing choices[0].message.content") from exc
        usage = data.get("usage", {}) or {}
        return ProviderResponse(
            text=str(content),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            reported_model=str(data.get("model", request.model_id)),
            execution_path=f"openai-compatible-{self.classification}",
            endpoint=self._base_url,
            raw={"classification": self.classification},
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
