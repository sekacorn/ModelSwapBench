"""What a provider failure may say in a stored result, and two related rules.

Each case's error is written to run.json and results.jsonl, so it carries a
status code or an exception type, never the upstream response body or the
wrapped exception's text. No socket is opened.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import httpx
import pytest

from model_swap_bench.config.models import ModelCandidate
from model_swap_bench.endpoints import endpoint_is_local
from model_swap_bench.errors import ProviderResponseError, ProviderUnavailableError
from model_swap_bench.providers import ollama as ollama_module
from model_swap_bench.providers.base import ProviderRequest
from model_swap_bench.providers.forge import ForgeProviderAdapter
from model_swap_bench.providers.ollama import OllamaProvider

MARKER = "upstream-text-2c7e-do-not-store"
ROOT = Path(__file__).resolve().parents[2]


def _request() -> ProviderRequest:
    return ProviderRequest(model_id="m", prompt="hi", system=None, temperature=0.0, max_tokens=8, timeout_seconds=5.0)


def _candidate(provider: str = "ollama") -> ModelCandidate:
    return ModelCandidate(alias="m", provider=provider, model="m", base_url="http://localhost:11434")


def _patch(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(ollama_module.httpx, "AsyncClient", factory)


@pytest.mark.parametrize("status", [400, 404, 500])
async def test_an_ollama_http_error_stores_the_status_not_the_body(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    _patch(monkeypatch, lambda request: httpx.Response(status, json={"error": f"detail {MARKER}"}))

    with pytest.raises(ProviderResponseError) as raised:
        await OllamaProvider(_candidate()).complete(_request())

    assert str(raised.value) == f"Ollama returned HTTP {status}"
    assert MARKER not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_an_ollama_connection_failure_stores_the_error_type_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"could not reach {request.url} {MARKER}", request=request)

    _patch(monkeypatch, handler)

    with pytest.raises(ProviderUnavailableError) as raised:
        await OllamaProvider(_candidate()).complete(_request())

    assert str(raised.value) == "cannot connect to Ollama (ConnectError)"
    assert raised.value.__cause__ is None


async def test_the_forge_adapter_stores_the_wrapped_error_type_only(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("forge")

    class Failing:
        async def complete(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(f"upstream said {MARKER}")

    adapter = ForgeProviderAdapter(_candidate("forge"))
    monkeypatch.setattr(adapter, "_get_provider", lambda: Failing())

    with pytest.raises(ProviderResponseError) as raised:
        await adapter.complete(_request())

    assert str(raised.value) == "Forge provider call failed (RuntimeError)"
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("url", ["http://[bad", "http://[::1", "https://[zz]/v1"])
def test_a_url_that_cannot_be_parsed_is_hosted_not_an_exception(url: str) -> None:
    # The same answer AgentForge and the AI Infrastructure Suite give.
    assert endpoint_is_local(url) is False


def test_the_agentforge_floor_excludes_the_versions_that_repeat_upstream_text() -> None:
    # 0.5.5 stopped repeating upstream error text; 0.5.6 also stopped logging a
    # token carried in a URL's query string.
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirement = next(r for r in project["dependencies"] if r.startswith("agentforge-oss"))

    assert requirement == "agentforge-oss>=0.5.6,<0.6.0"
