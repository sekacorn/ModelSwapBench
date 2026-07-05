# Contributor handoff

A guided tour for the next maintainer. Read [ARCHITECTURE.md](../ARCHITECTURE.md)
first; this page covers "where do I change X".

## Code map

| I want to… | Look at |
|---|---|
| Change the YAML format | `config/models.py` (+ regenerate schema via `config/schema.py`) |
| Add cross-field validation | `config/validation.py` |
| Add a provider | `providers/` + `providers/base.py::build_provider` (docs/adding-a-provider.md) |
| Add an evaluator | `evaluators/` + register + `KNOWN_EVALUATORS` (docs/adding-an-evaluator.md) |
| Change how cases execute | `execution/runner.py::run_case` |
| Change escalation logic | `execution/cascade.py::should_escalate` |
| Change metrics | `scoring/aggregation.py`, `scoring/metrics.py` |
| Change cost math | `scoring/economics.py` |
| Change recommendations | `scoring/replacement.py::decide_replacement` |
| Change storage layout | `storage/repository.py`, `storage/files.py`, `storage/sqlite.py` |
| Change reports | `reports/markdown.py` (others render from the same run model) |
| Add a CLI command | `cli/commands.py` (logic) + `cli/app.py` (Typer wiring) |

## Invariants to preserve

1. Tests run fully offline; the deterministic provider is the test workhorse.
2. `yaml.safe_load` only; no code execution from benchmark files.
3. Hosted providers stay opt-in; `execution_path` is always honest.
4. Zero-success economics return `None`, never divide by zero.
5. Failures are never hidden behind aggregate scores (see the success-rate-drop
   gate in `decide_replacement`).
6. All writes stay inside `.modelswapbench/` via `security/paths.py`.

## Release procedure (when publication is authorized)

1. Bump `model_swap_bench/_version.py` **and** `pyproject.toml` (kept in sync manually).
2. Update `CHANGELOG.md`.
3. `make quality && make build`.
4. Tag `vX.Y.Z` — `release.yml` builds artifacts + checksums (publishing must be
   explicitly configured; it is intentionally absent).

## Suggested first contributor issues

See the list at the end of [reports/v0.1-verification.md](../reports/v0.1-verification.md).
