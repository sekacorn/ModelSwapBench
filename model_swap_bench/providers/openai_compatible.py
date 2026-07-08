"""OpenAI-compatible provider for self-hosted endpoints (vLLM, llama.cpp, LM Studio, gateways).

Disabled unless a ``base_url`` is configured. Endpoints are classified as local or
external; external endpoints require ``--allow-hosted`` because data would leave
the machine. API keys are read from an environment variable (never stored in the
suite) and are never written to results or reports.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

import httpx

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.errors import (
    ConfigError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse

_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def endpoint_is_local(base_url: str) -> bool:
    """Classify an endpoint as local (loopback / private network) or external."""
    host = urlparse(base_url).hostname or ""
    if host in _LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


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
        self._client: httpx.AsyncClient | None = None

    @property
    def classification(self) -> str:
        return "local" if self._is_local else "external"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, headers=headers)
        return self._client

    async def health(self) -> HealthStatus:
        try:
            resp = await self._get_client().get("/models")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return HealthStatus(
                available=False,
                detail=f"cannot reach OpenAI-compatible endpoint ({self.classification}): {exc}",
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
            raise ProviderUnavailableError(f"endpoint unreachable: {exc}") from exc
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
