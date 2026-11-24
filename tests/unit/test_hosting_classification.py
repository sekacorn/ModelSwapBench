"""Whether a candidate sends content off the machine, decided by its endpoint.

Before this was derived, ``ModelCandidate.is_hosted`` asked only whether the
provider *kind* was in a fixed set. ``openai_compatible`` is not in that set and
``deployment`` defaults to ``local``, so a candidate pointed at a vendor's URL
reported as local. The visible consequence was in costing: a per-token-billed
endpoint with no declared pricing was reported as free rather than unknown.

Nothing here opens a socket. ``endpoint_is_local`` never resolves a name, so
every case is a pure string and address classification.
"""

from __future__ import annotations

import pytest

from model_swap_bench.config.models import (
    HOSTED_PROVIDERS,
    DeploymentType,
    ModelCandidate,
    ProviderKind,
    ScoringConfig,
)
from model_swap_bench.endpoints import endpoint_is_local
from model_swap_bench.scoring.economics import estimate_call_cost


def _candidate(**overrides: object) -> ModelCandidate:
    base: dict[str, object] = {
        "alias": "m",
        "provider": ProviderKind.OPENAI_COMPATIBLE,
        "model": "x",
    }
    base.update(overrides)
    return ModelCandidate.model_validate(base)


# --- the bug ---------------------------------------------------------------


def test_a_compatible_endpoint_at_a_vendor_url_is_hosted() -> None:
    # The regression this fix exists for. Default deployment is local and
    # openai_compatible is not in HOSTED_PROVIDERS, so the old enum test said
    # local for an endpoint that plainly is not.
    candidate = _candidate(base_url="https://api.vendor.example/v1")

    assert candidate.is_hosted
    assert ProviderKind.OPENAI_COMPATIBLE not in HOSTED_PROVIDERS
    assert candidate.deployment is DeploymentType.LOCAL


def test_an_unpriced_vendor_endpoint_costs_unknown_not_free() -> None:
    # The consequence that matters: reporting a per-token-billed vendor as
    # free is worse than reporting it as unknown, because a zero is a number
    # someone will compare against.
    candidate = _candidate(base_url="https://api.vendor.example/v1")

    cost = estimate_call_cost(candidate, ScoringConfig(), input_tokens=1000, output_tokens=500, latency_ms=250.0)

    assert cost is None


def test_an_unpriced_local_endpoint_still_costs_a_known_zero() -> None:
    # Local inference has no marginal per-token vendor charge, so absent
    # pricing there is genuinely zero rather than unknown. The fix must not
    # turn every missing price into None.
    candidate = _candidate(base_url="http://localhost:8000/v1")

    cost = estimate_call_cost(candidate, ScoringConfig(), input_tokens=1000, output_tokens=500, latency_ms=250.0)

    assert cost == 0.0


# --- the classification matrix --------------------------------------------


@pytest.mark.parametrize(
    ("label", "overrides", "expected"),
    (
        ("vendor url", {"base_url": "https://api.vendor.example/v1"}, True),
        ("localhost", {"base_url": "http://localhost:8000/v1"}, False),
        ("loopback v4", {"base_url": "http://127.0.0.1:1234/v1"}, False),
        ("private lan", {"base_url": "http://192.168.1.5:8000/v1"}, False),
        ("private 10/8", {"base_url": "http://10.0.0.7:8000/v1"}, False),
        ("unspecified", {"base_url": "http://0.0.0.0:8000/v1"}, False),
        ("ollama remote", {"provider": ProviderKind.OLLAMA, "base_url": "https://ollama.example"}, True),
        ("ollama local", {"provider": ProviderKind.OLLAMA, "base_url": "http://localhost:11434"}, False),
        ("ollama no url", {"provider": ProviderKind.OLLAMA}, False),
        ("openai, no url", {"provider": ProviderKind.OPENAI}, True),
        ("anthropic, no url", {"provider": ProviderKind.ANTHROPIC}, True),
        ("bedrock, no url", {"provider": ProviderKind.BEDROCK}, True),
        ("deterministic", {"provider": ProviderKind.DETERMINISTIC, "deployment": "test"}, False),
    ),
)
def test_hosting_is_derived_from_the_endpoint(label: str, overrides: dict[str, object], expected: bool) -> None:
    assert _candidate(**overrides).is_hosted is expected, label


def test_a_declaration_can_add_hosted_ness_but_not_remove_it() -> None:
    # Declaring hosted for a local endpoint is honoured: an operator may know
    # something about the deployment that the URL does not show.
    assert _candidate(base_url="http://localhost:8000/v1", deployment=DeploymentType.HOSTED).is_hosted

    # Declaring self_hosted for a public endpoint is not: whoever owns the
    # server, the content still left this machine.
    assert _candidate(base_url="https://vps.example.com/v1", deployment=DeploymentType.SELF_HOSTED).is_hosted

    # And a local declaration cannot talk a public endpoint down either.
    assert _candidate(base_url="https://api.vendor.example/v1", deployment=DeploymentType.LOCAL).is_hosted


# --- the endpoint rule itself ---------------------------------------------


@pytest.mark.parametrize(
    "url",
    (
        "http://localhost:8000/v1",
        "http://127.0.0.1",
        "http://[::1]:8000",
        "http://192.168.1.5",
        "http://172.16.0.1",
        "http://10.1.2.3",
        "http://169.254.1.1",
        "http://0.0.0.0:11434",
    ),
)
def test_local_endpoints_are_recognised(url: str) -> None:
    assert endpoint_is_local(url)


@pytest.mark.parametrize(
    "url",
    (
        "https://api.vendor.example/v1",
        "https://8.8.8.8/v1",
        "http://example.com",
        # A name is not a route: this is never resolved, so a hostname that
        # happens to point somewhere private is still treated as external.
        "http://db.internal.corp/v1",
        # Unclassifiable input fails to the safe side.
        "",
        "not a url",
        "https://",
    ),
)
def test_anything_not_positively_local_is_external(url: str) -> None:
    assert not endpoint_is_local(url)


def test_the_rule_performs_no_name_resolution() -> None:
    # Resolution would be a network call, and a name that resolves privately
    # today may not tomorrow. Asserted by making resolution fail loudly.
    import socket

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("endpoint classification must not resolve names.")

    original = socket.getaddrinfo
    socket.getaddrinfo = refuse  # type: ignore[assignment]
    try:
        assert not endpoint_is_local("http://db.internal.corp/v1")
        assert endpoint_is_local("http://localhost:8000")
    finally:
        socket.getaddrinfo = original  # type: ignore[assignment]


def test_the_helper_is_still_importable_from_the_provider_module() -> None:
    # It moved so the configuration layer could share one rule, and the old
    # import path is kept rather than broken for no gain.
    from model_swap_bench.providers.openai_compatible import (
        endpoint_is_local as from_provider,
    )

    assert from_provider is endpoint_is_local


def test_the_provider_gate_and_the_config_property_agree(caplog: pytest.LogCaptureFixture) -> None:
    # Two layers asking the same question must not be able to answer
    # differently: that disagreement is what let a hosted run be costed as
    # local while still being refused at execution time.
    from model_swap_bench.providers.openai_compatible import OpenAICompatibleProvider

    for url in ("https://api.vendor.example/v1", "http://localhost:8000/v1"):
        candidate = _candidate(base_url=url)
        provider = OpenAICompatibleProvider(candidate, allow_hosted=True)
        assert (provider.classification == "external") is candidate.is_hosted, url
