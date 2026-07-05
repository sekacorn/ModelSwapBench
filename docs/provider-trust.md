# Provider trust

Providers differ in where your data goes and how much you must trust them.

| Provider | Data leaves machine? | Trust notes |
|---|---|---|
| deterministic | No | Fully offline test double |
| ollama | No (local endpoint) | Trust your local Ollama install |
| forge | No (routes to local Ollama) | Trust agentforge-oss + local Ollama |
| openai_compatible (local) | No | Trust your self-hosted server |
| openai_compatible (external) | **Yes** | Requires `--allow-hosted`; data leaves the machine |
| openai / anthropic / bedrock | **Yes** | Hosted; opt-in extras; explicit permission + warning |

## Endpoint classification

`openai_compatible` classifies endpoints as **local** (loopback / private network)
or **external**. External endpoints require `--allow-hosted`. The classification is
recorded in each result's `execution_path`.

## Credentials

API keys are read from the environment variable named in `api_key_env` — the suite
never contains the key. Keys are never written to results or reports, and are
redacted from logs.

## Trust checklist before enabling a hosted provider

1. Is the benchmark data safe to send off-machine?
2. Do you trust the endpoint operator's retention/logging policy?
3. Have you set `privacy.allow_hosted_providers: true` intentionally?
