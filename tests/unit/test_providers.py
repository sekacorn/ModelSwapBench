from __future__ import annotations

import pytest

from model_swap_bench.config.models import ModelCandidate, ProviderKind
from model_swap_bench.errors import ProviderResponseError, ProviderTimeoutError, ProviderUnavailableError
from model_swap_bench.providers.base import ProviderRequest, build_provider
from model_swap_bench.providers.deterministic import DeterministicProvider
from model_swap_bench.providers.openai_compatible import OpenAICompatibleProvider, endpoint_is_local


def _cand(**kw: object) -> ModelCandidate:
    base = {"alias": "m", "provider": ProviderKind.DETERMINISTIC, "model": "x", "deployment": "test"}
    base.update(kw)
    return ModelCandidate.model_validate(base)


async def test_deterministic_oracle() -> None:
    p = DeterministicProvider(_cand(metadata={"strategy": "oracle"}))
    r = await p.complete(ProviderRequest(model_id="x", prompt="p", case_id="c", expected={"a": 1}))
    assert r.text == '{"a": 1}'
    assert (await p.health()).available


async def test_deterministic_static() -> None:
    p = DeterministicProvider(_cand(metadata={"strategy": "static", "output": "hello"}))
    r = await p.complete(ProviderRequest(model_id="x", prompt="p"))
    assert r.text == "hello"


async def test_deterministic_fixture_error_and_timeout(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fixture = tmp_path / "f.yaml"
    fixture.write_text(
        "cases:\n  boom: {status: error}\n  slow: {status: timeout}\n  ok: {output: '{\"x\": 1}', tokens: {input: 3, output: 2}}\n",
        encoding="utf-8",
    )
    p = DeterministicProvider(_cand(fixture="f.yaml", metadata={"strategy": "fixture"}), suite_dir=tmp_path)
    with pytest.raises(ProviderResponseError):
        await p.complete(ProviderRequest(model_id="x", prompt="p", case_id="boom"))
    with pytest.raises(ProviderTimeoutError):
        await p.complete(ProviderRequest(model_id="x", prompt="p", case_id="slow"))
    ok = await p.complete(ProviderRequest(model_id="x", prompt="p", case_id="ok"))
    assert ok.output_tokens == 2


def test_build_provider_hosted_refused() -> None:
    cand = _cand(provider=ProviderKind.OPENAI, deployment="hosted")
    with pytest.raises(ProviderUnavailableError):
        build_provider(cand, allow_hosted=False)


def test_endpoint_classification() -> None:
    assert endpoint_is_local("http://localhost:8000/v1")
    assert endpoint_is_local("http://127.0.0.1:8000")
    assert endpoint_is_local("http://192.168.1.5:8000")
    assert not endpoint_is_local("https://api.example.com/v1")


def test_openai_compatible_external_needs_allow_hosted() -> None:
    cand = _cand(provider=ProviderKind.OPENAI_COMPATIBLE, base_url="https://api.example.com/v1")
    with pytest.raises(ProviderUnavailableError):
        OpenAICompatibleProvider(cand, allow_hosted=False)
    # local is fine without allow_hosted
    local = OpenAICompatibleProvider(_cand(provider=ProviderKind.OPENAI_COMPATIBLE, base_url="http://localhost:8000/v1"))
    assert local.classification == "local"


async def test_ollama_health_unreachable() -> None:
    from model_swap_bench.providers.ollama import OllamaProvider

    cand = _cand(provider=ProviderKind.OLLAMA, model="qwen2.5:3b", base_url="http://127.0.0.1:9", timeout_seconds=1.0)
    p = OllamaProvider(cand)
    health = await p.health()
    await p.aclose()
    assert not health.available
