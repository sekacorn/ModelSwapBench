# Contributing to ModelSwapBench

Thanks for your interest! ModelSwapBench is Apache-2.0-licensed and provider-neutral by
design — contributions should preserve both.

## Getting started

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,security,quality]"   # Windows: .venv\Scripts\python
make quality      # lint + typecheck + test + security
```

## Ground rules

- **Tests must pass offline** — no paid APIs, internet, Ollama, Docker, or GPU
  required for the default suite. Use the deterministic provider.
- **Typed and linted**: `ruff` clean, `mypy --strict` clean.
- **≥ 80% meaningful coverage** — no superficial tests to pad the number.
- **No incompatible source code** may be copied in. All original code is Apache-2.0 licensed.
- **Provider neutrality**: don't hard-code a single vendor into core logic.
- **Honesty**: never fabricate results, prices, or benchmark scores.

## Extending

- Add a provider: implement `providers.base.Provider`; see
  [docs/adding-a-provider.md](docs/adding-a-provider.md).
- Add an evaluator: subclass `evaluators.base.Evaluator` and `@register`; see
  [docs/adding-an-evaluator.md](docs/adding-an-evaluator.md).

## Pull requests

Keep PRs focused. Update docs and `CHANGELOG.md`. Ensure `make quality` and
`make build` pass. Good first issues are listed in `reports/v0.1-verification.md`.
