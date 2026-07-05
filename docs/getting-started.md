# Getting started

## Install

```bash
git clone https://github.com/sekacorn/ModelSwapBench.git
cd ModelSwapBench
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -e ".[dev]"
# Linux/macOS:
.venv/bin/python -m pip install -e ".[dev]"
```

## First run (fully offline)

```bash
modelswapbench doctor
modelswapbench validate examples/support-ticket-triage/benchmark.yaml
modelswapbench run examples/support-ticket-triage/benchmark.yaml
modelswapbench compare latest
modelswapbench report latest --format markdown
```

The support-ticket example uses the deterministic provider — no model downloads,
no credentials. It compares a simulated priced baseline against a free local
candidate and produces a replacement recommendation with cost-per-success.

## Scaffold your own

```bash
modelswapbench init my-benchmark
modelswapbench run my-benchmark/benchmark.yaml
```

## Next steps

- [benchmark-format.md](benchmark-format.md) — the YAML format.
- [cost-per-success.md](cost-per-success.md) — the primary economic metric.
- [replacement-decisions.md](replacement-decisions.md) — how recommendations are made.
- [providers.md](providers.md) — running against Ollama or a local OpenAI-compatible server.
