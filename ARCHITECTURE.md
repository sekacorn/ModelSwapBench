# Architecture

ModelSwapBench is a layered, provider-neutral pipeline. Each layer has a single
responsibility and a typed boundary, so components (providers, evaluators,
pricing, storage) can be replaced without touching the rest.

## Layers

| Layer | Package | Responsibility |
|---|---|---|
| Config | `config/` | Typed Pydantic models, safe YAML loading, semantic validation, JSON Schema |
| Providers | `providers/` | Provider-neutral model calls: deterministic, Ollama, Forge, OpenAI-compatible |
| Execution | `execution/` | Runner, bounded concurrency, retries, timeouts, cascade, raw capture |
| Evaluators | `evaluators/` | Deterministic, pluggable, evidence-producing checks |
| Scoring | `scoring/` | Metrics, economics (cost/success), aggregation, replacement decisions |
| Storage | `storage/` | SQLite index + filesystem artifacts + reproducibility manifests |
| Reports | `reports/` | Markdown, JSON, CSV, HTML renderers |
| Pricing | `pricing/` | Editable, versioned, offline pricing registry |
| Security | `security/` | Path-safety and secret redaction |
| CLI | `cli/` | Typer app, doctor, commands, output |

## Data flow

```
benchmark.yaml
   │  load + validate (config)
   ▼
BenchmarkSuite ──► BenchmarkRunner (execution)
                      │  build_provider() per model
                      ▼
                   Provider.complete()  ──► ProviderResponse
                      │
                      ▼
                   Evaluators ──► EvaluationResult (evidence)
                      │
                      ▼
                   CaseResult ──► aggregation ──► ModelSummary
                      │                              │
                      │                              ▼
                      │                    replacement decision engine
                      ▼                              │
                   BenchmarkRun ◄───────────────────┘
                      │  save (storage: sqlite + files + manifest)
                      ▼
                   reports (md / json / csv / html)
```

## Trust boundaries

- **Benchmark files** are untrusted data: loaded with `yaml.safe_load`, never
  executed. No custom Python evaluators in v0.1.
- **Model output** is untrusted: bounded in size, HTML-escaped in reports, and
  parsed defensively.
- **Providers**: hosted providers are refused unless explicitly permitted. API
  keys come from the environment and never enter results.
- **Filesystem**: all writes are confined to the storage directory via
  `security.paths` (traversal + symlink guards).

## Key design decisions

- **Deterministic provider** makes the whole pipeline testable and demoable fully
  offline, and can simulate failures for cascade/escalation.
- **Cost per success** is the primary economic metric; zero-success is `None`, not
  a crash.
- **Replacement decisions** are rules-based and carry evidence — no black-box score.
- **SQLite + files** over a server database keeps everything local and portable.
