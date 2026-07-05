"""Optional integration tests — require a running local Ollama with qwen2.5:3b.

Run explicitly with: pytest -m integration
They are excluded from the default suite and CI (`-m "not integration"`).
"""

from __future__ import annotations

import httpx
import pytest

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.providers.base import ProviderRequest
from model_swap_bench.providers.forge import ForgeProviderAdapter
from model_swap_bench.providers.ollama import DEFAULT_BASE_URL, OllamaProvider

pytestmark = pytest.mark.integration

MODEL = "qwen2.5:3b"


def _ollama_available() -> bool:
    try:
        resp = httpx.get(f"{DEFAULT_BASE_URL}/api/tags", timeout=2.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return False
    names = {m.get("name", "") for m in resp.json().get("models", [])}
    return any(n.startswith(MODEL) for n in names)


requires_ollama = pytest.mark.skipif(not _ollama_available(), reason=f"Ollama with {MODEL} not available")


def _candidate(kind: ProviderKind) -> ModelCandidate:
    return ModelCandidate(alias="it", provider=kind, model=MODEL, deployment="local", timeout_seconds=120.0)


@requires_ollama
async def test_ollama_direct_completion() -> None:
    provider = OllamaProvider(_candidate(ProviderKind.OLLAMA))
    try:
        health = await provider.health()
        assert health.available, health.detail
        response = await provider.complete(
            ProviderRequest(model_id=MODEL, prompt="Reply with exactly: pong", max_tokens=16, timeout_seconds=120.0)
        )
        assert response.text.strip()
        assert response.execution_path == "ollama-direct"
    finally:
        await provider.aclose()


@requires_ollama
async def test_forge_adapter_completion() -> None:
    provider = ForgeProviderAdapter(_candidate(ProviderKind.FORGE))
    try:
        health = await provider.health()
        assert health.available, health.detail
        response = await provider.complete(
            ProviderRequest(model_id=MODEL, prompt="Reply with exactly: pong", max_tokens=16, timeout_seconds=120.0)
        )
        assert response.text.strip()
        assert response.execution_path == "forge->ollama"
    finally:
        await provider.aclose()
