"""A base_url that carries credentials is refused, and never repeated.

Run artefacts record every model's endpoint (manifest.json, run.json,
results.jsonl, suite.json) and the HTTP client logs each request URL, so a
password placed in a base_url used to be written to all of them. It is now
refused when the suite loads, and again where a provider is built.

No test here opens a socket: refused configurations never reach a provider,
and the one end-to-end run answers from an in-process transport.
"""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from model_swap_bench.cli.app import app
from model_swap_bench.config import build_suite, load_suite
from model_swap_bench.config.models import ModelCandidate
from model_swap_bench.endpoints import url_has_credentials
from model_swap_bench.errors import ConfigError
from model_swap_bench.execution import BenchmarkRunner
from model_swap_bench.providers import openai_compatible as oc
from model_swap_bench.providers.forge import ForgeProviderAdapter
from model_swap_bench.providers.ollama import OllamaProvider
from model_swap_bench.providers.openai_compatible import OpenAICompatibleProvider
from model_swap_bench.storage import RunRepository
from tests.conftest import make_suite_dict

SECRET = "secret-4c1e-do-not-log"
_WITH_CREDENTIALS = [
    f"https://user:{SECRET}@host/v1",
    f"https://{SECRET}@llm.example.test/v1",
    f"https://:{SECRET}@llm.example.test/v1",
    f"http://user:{SECRET}@localhost:8000/v1",
    f"http://user:{SECRET}@127.0.0.1:11434",
    f"https://user:{SECRET}@[::1]:8000/v1",
    f"https://user:{SECRET}@llm.example.test:notaport/v1",
]
_CLEAN = [
    "https://llm.example.test/v1",
    "http://localhost:8000/v1",
    "https://llm.example.test/v1/path@with-at",
    "https://llm.example.test/v1?user=a@b",
]


def _rendered(error: BaseException) -> str:
    """Everything a log line, an error report or a traceback could print."""
    return "\n".join([str(error), repr(error), "".join(traceback.format_exception(type(error), error, error.__traceback__))])


def _suite_dict(base_url: str, provider: str = "openai_compatible") -> dict[str, Any]:
    d = make_suite_dict()
    d["models"][1] = {
        "alias": "candidate",
        "provider": provider,
        "model": "cand",
        "base_url": base_url,
        "deployment": "hosted",
    }
    d["privacy"] = {"allow_hosted_providers": True}
    return d


@pytest.mark.parametrize("url", _WITH_CREDENTIALS)
def test_credentials_in_a_url_are_detected(url: str) -> None:
    assert url_has_credentials(url)


@pytest.mark.parametrize("url", _CLEAN)
def test_an_at_sign_outside_the_authority_is_not_a_credential(url: str) -> None:
    assert not url_has_credentials(url)


@pytest.mark.parametrize("provider", ["openai_compatible", "ollama", "forge"])
@pytest.mark.parametrize("url", _WITH_CREDENTIALS)
def test_a_suite_with_credentials_in_base_url_is_refused(url: str, provider: str) -> None:
    with pytest.raises(ConfigError) as raised:
        build_suite(_suite_dict(url, provider))

    assert "must not contain credentials" in str(raised.value)
    assert SECRET not in _rendered(raised.value)


def test_a_suite_file_with_credentials_is_refused_without_echoing_them(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(_suite_dict(_WITH_CREDENTIALS[0])), encoding="utf-8")

    with pytest.raises(ConfigError) as raised:
        load_suite(path)

    assert SECRET not in _rendered(raised.value)


def test_the_cli_refuses_the_file_without_printing_the_secret(tmp_path: Path) -> None:
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(_suite_dict(_WITH_CREDENTIALS[0])), encoding="utf-8")

    result = CliRunner().invoke(app, ["validate", str(path)])

    assert result.exit_code != 0
    assert SECRET not in result.output
    assert "must not contain credentials" in result.output


def test_a_candidate_built_directly_is_refused() -> None:
    with pytest.raises(ValueError) as raised:
        ModelCandidate(alias="m", provider="openai_compatible", model="x", base_url=_WITH_CREDENTIALS[0])

    assert SECRET not in _rendered(raised.value)


@pytest.mark.parametrize("provider_class", [OpenAICompatibleProvider, OllamaProvider, ForgeProviderAdapter])
def test_a_provider_refuses_a_candidate_that_skipped_validation(provider_class: type) -> None:
    # model_construct() bypasses validators; the provider checks again.
    candidate = ModelCandidate.model_construct(
        alias="m", provider="openai_compatible", model="x", base_url=_WITH_CREDENTIALS[0], timeout_seconds=None
    )

    with pytest.raises(ConfigError) as raised:
        provider_class(candidate)

    assert SECRET not in _rendered(raised.value)


async def test_a_clean_hosted_endpoint_still_runs_and_stores_no_userinfo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        body = {"category": "billing", "escalation_required": True}
        return httpx.Response(200, json={"model": "cand", "choices": [{"message": {"content": json.dumps(body)}}]})

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(oc.httpx, "AsyncClient", factory)
    suite = build_suite(_suite_dict("https://llm.example.test/v1"))

    with caplog.at_level(logging.INFO):
        run = await BenchmarkRunner(suite, allow_hosted=True).run()
        RunRepository(tmp_path).save(run, suite)

    written = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl"}]
    assert {p.name for p in written} >= {"manifest.json", "run.json", "results.jsonl", "suite.json"}
    for path in written:
        assert "@llm.example.test" not in path.read_text(encoding="utf-8")
    assert "@llm.example.test" not in caplog.text


# --- fragments and query strings, and default_query ---------------------------

_OTHER_BAD_URLS = {
    "fragment": f"https://llm.example.test/v1#{SECRET}",
    "query": f"https://llm.example.test/v1?key={SECRET}",
    "empty query": "https://llm.example.test/v1?",
}
API_VERSION = "2099-01-01-preview-5e1b"


@pytest.mark.parametrize("provider", ["openai_compatible", "ollama", "forge"])
@pytest.mark.parametrize("case", sorted(_OTHER_BAD_URLS))
def test_a_fragment_or_query_in_base_url_is_refused(case: str, provider: str) -> None:
    with pytest.raises(ConfigError) as raised:
        build_suite(_suite_dict(_OTHER_BAD_URLS[case], provider))

    assert "base_url must not contain" in str(raised.value)
    assert SECRET not in _rendered(raised.value)


def _with_default_query(value: Any) -> dict[str, Any]:
    d = _suite_dict("https://llm.example.test/v1")
    d["models"][1]["default_query"] = value
    return d


@pytest.mark.parametrize(
    "bad",
    [{"bad key": "v"}, {"k": ""}, {"k": "x" * 513}, {f"k{i}": "v" for i in range(17)}, {"k": 5}],
)
def test_a_malformed_default_query_is_refused_without_echo(bad: Any) -> None:
    with pytest.raises(ConfigError) as raised:
        build_suite(_with_default_query(bad))

    assert "x" * 50 not in _rendered(raised.value)


def test_default_query_is_only_for_the_provider_that_sends_it() -> None:
    d = _suite_dict("http://localhost:11434", "ollama")
    d["models"][1]["default_query"] = {"api-version": API_VERSION}

    with pytest.raises(ConfigError, match="only sent by the openai_compatible"):
        build_suite(d)


def test_default_query_values_are_never_serialized() -> None:
    suite = build_suite(_with_default_query({"api-version": API_VERSION}))
    candidate = suite.models[1]

    assert candidate.default_query == {"api-version": API_VERSION}
    assert candidate.model_dump()["default_query"] == {"api-version": "[redacted]"}
    assert API_VERSION not in suite.model_dump_json()


async def test_default_query_reaches_the_endpoint_and_no_artefact_or_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    real = httpx.AsyncClient
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        body = {"category": "billing", "escalation_required": True}
        return httpx.Response(200, json={"model": "cand", "choices": [{"message": {"content": json.dumps(body)}}]})

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(oc.httpx, "AsyncClient", factory)
    suite = build_suite(_with_default_query({"api-version": API_VERSION}))

    with caplog.at_level(logging.DEBUG):
        run = await BenchmarkRunner(suite, allow_hosted=True).run()
        RunRepository(tmp_path).save(run, suite)

    assert seen and all(url.params.get("api-version") == API_VERSION for url in seen)
    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert {p.name for p in written} >= {"manifest.json", "run.json", "results.jsonl", "suite.json"}
    for path in written:
        assert API_VERSION.encode() not in path.read_bytes(), path.name
    assert API_VERSION not in caplog.text
    manifest = json.loads(next(p for p in written if p.name == "manifest.json").read_text(encoding="utf-8"))
    assert manifest["models"][1]["default_query_params"] == ["api-version"]


async def test_an_unreachable_endpoint_reports_the_error_type_only(monkeypatch: pytest.MonkeyPatch) -> None:
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"could not reach {request.url}", request=request)

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(oc.httpx, "AsyncClient", factory)
    suite = build_suite(_with_default_query({"api-version": API_VERSION}))

    run = await BenchmarkRunner(suite, allow_hosted=True).run()

    errors = [r.error for r in run.case_results if r.model_alias == "candidate"]
    assert errors and all(e == "endpoint unreachable (ConnectError)" for e in errors)
