# Providers

All providers implement the same `Provider` interface (`health()` + `complete()`)
and return provider-neutral responses.

## deterministic

Offline, reproducible test provider. No network, no downloads. Strategies via
`metadata.strategy`:

- `oracle` — emits the case's expected output (a perfect model).
- `fixture` — emits explicit per-case outputs from a `fixture:` file (can simulate
  wrong answers, invalid JSON, tool calls, latency, tokens, errors, timeouts).
- `static` — emits a fixed `metadata.output` string.

Used by every offline example and the entire test suite.

## ollama (default real provider)

Local model execution via the Ollama HTTP API.

- `base_url` (default `http://localhost:11434`), `timeout_seconds`.
- Health check verifies the endpoint **and** that the model is present.
- Never pulls models automatically; never falls back to a hosted service.
- Records the model name Ollama reports plus token counts when available.

```bash
ollama pull qwen2.5:3b
# set provider: ollama, model: qwen2.5:3b, deployment: local
```

## forge (agentforge-oss adapter)

Routes calls through the `agentforge-oss` provider API and records
`execution_path=forge->ollama`, so a Forge call is never misreported as a direct
call. v0.1 exercises Forge's provider layer, not full agent orchestration (roadmap).

## openai_compatible (self-hosted)

For vLLM, llama.cpp servers, LM Studio-compatible services, and local gateways.

- Requires `base_url`. Classifies the endpoint as **local** or **external**.
- External endpoints require `--allow-hosted` (data would leave the machine).
- API key read from `api_key_env`; never written to results/reports.

## Optional hosted adapters (extras)

`openai`, `anthropic`, `bedrock` may be added behind extras. They require explicit
configuration and benchmark permission, and are **not** required for v0.1. See
[provider-trust.md](provider-trust.md).
