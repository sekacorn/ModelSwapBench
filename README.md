# ModelSwapBench

**Open-source model portability testing for real AI workflows.**

Run the same workflow across local, open-weight, self-hosted, and hosted models.
Measure quality, latency, policy compliance, and **cost per successful outcome**
before you commit to a vendor.

> Status: **v0.1.0-alpha** — usable and fully offline-capable. APIs may change before 1.0.

---

## Why it exists

Teams are told a cheaper or local model "can't replace" their expensive hosted
model — but rarely with evidence tied to the actual workflow. ModelSwapBench
answers the real question:

> Can a cheaper, local, open-weight, or alternative-provider model replace my
> current model **without breaking my workflow** — and what does it cost per
> successful outcome?

It is a **decision-support tool for model replacement**, not a leaderboard, not a
foundation-model laboratory, and not proof that one model is universally better.

## Anti-lock-in by design

- Provider-neutral benchmark definitions in plain **YAML/JSON** you own and edit.
- Portable **JSON, CSV, Markdown, and HTML** reports; raw results always exportable.
- Standard HTTP provider interfaces; **OpenAI-compatible** local endpoints; **Ollama**; **Forge**.
- **No** mandatory hosted service, account, cloud database, or telemetry.
- Replaceable model adapters, evaluators, and pricing registries.
- Everything runs **local-first**; hosted providers are opt-in per suite.

## Architecture

```
benchmark.yaml ─► config (typed, validated) ─► runner ─► providers ─► models
                                                  │
                                     evaluators ◄─┘ (deterministic, evidence-based)
                                                  │
             scoring / economics / replacement ◄──┘
                                                  │
        storage (SQLite index + files) ◄──────────┤──► reports (md/json/csv/html)
                                                  │
                          reproducibility manifest
```

## Five-minute offline example (no downloads, no credentials)

Install from PyPI:

```bash
python -m pip install modelswapbench
```

Install this repository for development:

```bash
git clone https://github.com/sekacorn/ModelSwapBench.git
cd ModelSwapBench
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -e ".[dev]"
# Linux/macOS:
.venv/bin/python -m pip install -e ".[dev]"

modelswapbench doctor
modelswapbench validate examples/support-ticket-triage/benchmark.yaml
modelswapbench run examples/support-ticket-triage/benchmark.yaml
modelswapbench report latest --format markdown
modelswapbench compare latest
modelswapbench exit-report --baseline openai:gpt-4o --candidate ollama:qwen2.5:3b \
  --input examples/vendor_exit/customer_support_results.json \
  --output reports/vendor_exit_report.md --format markdown
modelswapbench route-plan \
  --input examples/route_plan/customer_support_routing_results.json \
  --output reports/model_routing_plan.md \
  --format markdown \
  --baseline openai:gpt-4o \
  --candidate ollama:qwen2.5:3b \
  --export-json reports/model_routing_plan.json
```

The first example runs entirely with the **deterministic provider** — no paid
model credentials and no model downloads required.

## Run against a real local model (Ollama)

```bash
ollama pull qwen2.5:3b
# Edit a suite so a model uses: provider: ollama, model: qwen2.5:3b, deployment: local
modelswapbench run examples/support-ticket-triage/benchmark.yaml
```

No model is ever pulled automatically, and there is no silent hosted fallback.

## Benchmark YAML

```yaml
name: support-ticket-triage
version: "1.0"
baseline_model: hosted-baseline
models:
  - {alias: local-candidate, provider: ollama, model: qwen2.5:3b, deployment: local}
  - {alias: hosted-baseline, provider: deterministic, model: baseline-fixture, deployment: test}
cases:
  - id: duplicate-billing
    input: {message: "I was charged twice and need help."}
    expected: {category: billing, escalation_required: true}
evaluators: [json_parse, json_schema, field_match, forbidden_content]
constraints: {minimum_success_rate: 0.80, maximum_cost_per_success_usd: 0.05}
replacement: {baseline: hosted-baseline, candidates: [local-candidate], maximum_quality_drop: 0.05}
```

Print the full JSON Schema any time: `modelswapbench schema`.

## Cost per successful outcome

The primary economic metric is:

```
cost_per_success = total_cost / successful_cases
```

Zero successful cases is handled safely (reported as "n/a", never a divide error).
Cost can be computed as **zero-marginal** (token/API pricing) or **estimated
compute** (electricity, GPU amortization, cloud-GPU-equivalent) from an
operator-supplied profile. Estimates are always clearly labeled as estimates.

## Replacement recommendations

A candidate is recommended only when every required gate passes. The decision is
transparent and always carries its evidence — failures are never hidden behind an
aggregate score. Possible outcomes: recommended replacement · recommended with
conditions · suitable as first-stage model with escalation · not recommended ·
insufficient evidence.

## AI Vendor Exit Report

`modelswapbench exit-report` creates a CTO-friendly migration report from
deterministic benchmark summaries or fixture JSONL data. It answers whether a
candidate model appears good enough to replace a baseline model for a specific
workload, with quality retention, estimated cost reduction, latency change, risk
profile, limitations, and reproducibility details.

```bash
modelswapbench exit-report \
  --baseline openai:gpt-4o \
  --candidate ollama:qwen2.5:3b \
  --input examples/vendor_exit/customer_support_results.json \
  --output reports/vendor_exit_report.md \
  --format markdown \
  --risk-profile medium \
  --export-aimeter reports/aimeter_summary.json \
  --export-auditlog reports/audit_events.jsonl
```

Portable exports:

- `--export-aimeter PATH` writes an AIMeter OSS-style JSON summary for estimated cost, efficiency, latency, decision, and outcome measurement workflows.
- `--export-auditlog PATH` writes AIAuditLog-style JSONL audit events for carrying vendor-exit evidence into audit-review workflows.

These exports are deterministic, offline-first, and file-based. They do not add
runtime dependencies on AIMeter OSS or AIAuditLog, and they do not automatically
prove compliance.

Sample excerpt:

```markdown
# AI Vendor Exit Report

## Decision

**Candidate acceptable**

## Cost

- Caveat: estimated cost is not invoice-confirmed.
- Caveat: projected savings are not realized savings.
```

This helps reduce vendor lock-in by separating the replacement decision from
provider marketing: the organization can inspect its own workload evidence,
thresholds, and risk boundaries before migration. Passing the report does not
prove legal, regulatory, safety, or security compliance, and human review may
still be required for high-risk workflows.

## Model Routing Plan

`modelswapbench route-plan` helps teams reduce vendor lock-in gradually by
identifying which tasks can move to a candidate model, which should remain on
the baseline model, which require human review, and which should be escalated or
blocked.

```bash
modelswapbench route-plan \
  --input examples/route_plan/customer_support_routing_results.json \
  --output reports/model_routing_plan.md \
  --format markdown \
  --baseline openai:gpt-4o \
  --candidate ollama:qwen2.5:3b \
  --risk-profile medium \
  --export-json reports/model_routing_plan.json \
  --export-aimeter reports/route_aimeter_summary.json \
  --export-auditlog reports/route_audit_events.jsonl
```

The plan classifies each task as `candidate_model`, `baseline_model`,
`human_review`, or `blocked_or_escalate`, with quality, cost, latency, policy
notes, routing percentages, and blended estimated savings when enough cost data
exists.

Portable exports are deterministic, offline-first, and file-based:

- `--export-json PATH` writes the full machine-readable route plan.
- `--export-aimeter PATH` writes an AIMeter OSS-style route cost/outcome summary.
- `--export-auditlog PATH` writes AIAuditLog-style JSONL audit events.

These exports do not add runtime dependencies on AIMeter OSS or AIAuditLog.
Estimated cost is not invoice-confirmed, projected savings are not realized
savings, and route decisions are not legal, compliance, safety, or security
guarantees.

## Cascade strategy

Run a cheap/local model first and escalate only failing or low-confidence cases to
a stronger model. Reports escalation rate, combined success, and combined cost per
success — see `examples/cascade-routing`.

## Privacy

- Local providers allowed by default; **hosted providers denied by default**.
- Benchmark data never leaves the machine unless you pass `--allow-hosted` **and**
  set `privacy.allow_hosted_providers: true`, after an explicit warning.
- No telemetry, no uploads; raw outputs stored locally; secrets redacted from logs
  and reports; API keys are read from environment variables and never written out.

## Evaluators

`exact_match` · `contains` / `forbidden_content` · `regex` · `json_parse` ·
`json_schema` · `field_match` · `tool_selection` · `policy_compliance` ·
`citation` · `latency` · `cost` · optional `rubric` (keyword heuristic; never the
sole evaluator; judge-model mode on the roadmap).

## CLI

`doctor` · `init` · `validate` · `schema` · `models` · `providers` · `run` ·
`compare` · `report` · `exit-report` · `route-plan` · `runs list|show` · `reproduce` · `clean` ·
`pricing show|validate|set` · `examples list`.

Exit codes: `0` success · `1` constraints failed · `2` invalid input ·
`3` provider unavailable · `4` partial run · `5` internal error.

## Output formats

Markdown (human report), JSON (full machine record), CSV (per-model summary), and
self-contained HTML. Raw model outputs and evaluator evidence are stored per run.

## Reproducibility

Every run writes a manifest (suite hash, package/Forge/Python versions, platform,
models, execution params, seed, git commit). `modelswapbench reproduce RUN_ID`
re-runs the recorded suite and warns on version drift rather than pretending the
run is identical.

## Known limitations

- Results are evidence for a replacement decision, not proof one model is best.
- Cost figures are estimates, not measured billing.
- Deterministic providers simulate behavior; only Ollama / OpenAI-compatible runs
  reflect real models.
- Small case counts yield low-confidence decisions.
- The Forge adapter exercises the provider layer, not full agent orchestration (roadmap).

## Roadmap

**v0.1** deterministic + Ollama + Forge + OpenAI-compatible providers, YAML suites,
deterministic evaluators, cost/latency/reliability metrics, replacement decisions,
cascade analysis, JSON/CSV/Markdown reports, offline tests. **v0.2** richer hosted
adapters, compute-cost profiler, statistical confidence, variance analysis, CI
regression gates, HTML dashboards. **v0.3** benchmark registries, signed manifests,
distributed execution, richer tool-use evaluation.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [ARCHITECTURE.md](ARCHITECTURE.md), and
`docs/`. Issues and PRs welcome.

## License

MIT — Copyright (c) 2026 sekacorn. See [LICENSE](LICENSE). Dependency
licenses are listed in [docs/dependency-licenses.md](docs/dependency-licenses.md).
