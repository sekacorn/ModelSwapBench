# Dependency licenses

ModelSwapBench itself is MIT. Runtime dependencies and their licenses (as of
2026-07; verify with `pip-licenses` for your installed versions):

| Package | License | Purpose |
|---|---|---|
| pydantic | MIT | Typed config/result models, validation, JSON Schema |
| pyyaml | MIT | Safe YAML loading |
| jsonschema | MIT | JSON Schema evaluator |
| httpx | BSD-3-Clause | Ollama / OpenAI-compatible HTTP clients |
| typer | MIT | CLI |
| rich | MIT | Console output |
| agentforge-oss | MIT | Forge provider adapter |

Optional extras: `openai` (Apache-2.0), `anthropic` (MIT), `boto3` (Apache-2.0).

Dev/quality tooling (not shipped): pytest (MIT), pytest-cov (MIT), pytest-asyncio
(Apache-2.0), ruff (MIT), mypy (MIT), bandit (Apache-2.0), pip-audit (Apache-2.0),
build (MIT), twine (Apache-2.0), yamllint (GPL-3.0 — dev-only tool, not linked or
distributed with the package).

All are compatible with MIT distribution of this project's own code. No source
code from any incompatible project has been copied into this repository.
