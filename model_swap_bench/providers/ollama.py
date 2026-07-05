"""Direct Ollama provider (local-first default real backend).

Talks to the Ollama HTTP API. It never pulls models automatically and never
falls back to a hosted service — if the model is missing you get a clear,
structured error.
"""

from __future__ import annotations

from typing import Any

import httpx

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.errors import ProviderResponseError, ProviderTimeoutError, ProviderUnavailableError
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(Provider):
    """Local model execution via the Ollama HTTP API."""

    kind = ProviderKind.OLLAMA

    def __init__(self, candidate: ModelCandidate) -> None:
        super().__init__(candidate)
        self._base_url = (candidate.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = candidate.timeout_seconds or 120.0
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self._client

    async def health(self) -> HealthStatus:
        try:
            resp = await self._get_client().get("/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            return HealthStatus(
                available=False,
                detail=f"cannot reach Ollama at {self._base_url}: {exc}",
                endpoint=self._base_url,
            )
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        wanted = self.candidate.model
        has_model = wanted in names or f"{wanted}:latest" in names or any(n.startswith(f"{wanted}:") for n in names)
        if not has_model:
            return HealthStatus(
                available=False,
                detail=f"model {wanted!r} not present in Ollama (pull it with `ollama pull {wanted}`)",
                endpoint=self._base_url,
            )
        return HealthStatus(available=True, detail=f"Ollama reachable; {wanted} present", endpoint=self._base_url)

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        options: dict[str, Any] = {"temperature": request.temperature, "num_predict": request.max_tokens}
        if request.seed is not None:
            options["seed"] = request.seed
        payload = {"model": request.model_id, "messages": messages, "stream": False, "options": options}
        try:
            resp = await self._get_client().post("/api/chat", json=payload, timeout=request.timeout_seconds)
            resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Ollama call timed out after {request.timeout_seconds}s") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(f"cannot connect to Ollama at {self._base_url}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderResponseError(f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
        data = resp.json()
        content = data.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ProviderResponseError("Ollama response missing message.content")
        return ProviderResponse(
            text=content,
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            reported_model=str(data.get("model", request.model_id)),
            execution_path="ollama-direct",
            endpoint=self._base_url,
            raw={"done_reason": data.get("done_reason", "")},
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
