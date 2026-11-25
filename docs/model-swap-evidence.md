# Swap evidence (`model-swap-evidence.v1`)

A benchmark run that compared your current model with an alternative is
evidence that the workload could move. `modelswapbench swap-evidence` writes
that result as a small, versioned JSON document that another tool can read
without importing ModelSwapBench.

It is written for the AI Infrastructure Suite's `model_providers` lock-in
vector, which is still being built. Until the suite's reader ships, nothing
consumes this document; the format is published now so the two sides can be
tested against each other.

## Writing one

```bash
modelswapbench run benchmark.yaml
modelswapbench swap-evidence latest --candidate local_alt --output evidence/swap-local-alt.json
```

- The run must have a `replacement` section: the document describes that
  section's baseline against one of its candidates.
- `--candidate` may be left out when the run has exactly one candidate.
- Without `--output` the document is printed.
- One document covers one candidate. Run the command once per candidate.

## What it contains

| Section | Contents |
|---|---|
| `run` | The run id, its manifest hash, when it ran, the execution mode, and the suite's name and version. |
| `baseline`, `candidate` | Provider kind, model id, endpoint origin, the deployment you declared, and the summary numbers. |
| `thresholds` | The `replacement` limits the run was judged against, and whether hosted candidates were permitted. |
| `candidate_constraints` | The name and pass/fail of each suite-level constraint checked against the candidate. |
| `verdict` | ModelSwapBench's own recommendation and whether the candidate was eligible. |

The summary numbers are the sample, success, failure, error and timeout
counts, the quality score, `tool_accuracy`, `policy_pass_rate`, p95 latency,
`evidence_sufficient` and the recommended minimum sample size. Cases counted
in none of the four outcomes were skipped.

Three values are `null` when there is nothing to report, and a reader must
never treat `null` as a pass:

- `quality_score`, when no case executed;
- `tool_accuracy`, when no case exercised tool selection;
- `policy_pass_rate`, when no policy evidence was collected.

## What it leaves out

- **Prompts, outputs, case ids and error text.** Only aggregate numbers.
- **Full URLs.** Only the origin is written: scheme, host and port. A
  `base_url` with credentials, a query string or a fragment is already refused
  when the benchmark loads.
- **Cost.** A more expensive alternative still shows the workload can move, so
  a portability reader ignores cost and this document does not offer it.
- **Free-text reasons.** The verdict is a fixed set of values.

`endpoint_origin` is `null` when the provider has no endpoint of its own to
state: the deterministic provider, or a vendor SDK using its built-in default.
For `ollama` and `forge` without a `base_url`, the default
`http://localhost:11434` is written, because that is the endpoint they use.

## What a reader can and cannot conclude

Everything in the document is ModelSwapBench's own report of what it measured.
A reader can check that the numbers are consistent and that the verdict
follows from them. It cannot check that any model was actually run, or that
the measurements are real. Treat it as attested evidence with checkable
arithmetic, not as proof.

A candidate from the `deterministic` provider is a fake. The document reports
it honestly (`provider_kind: deterministic`), and a reader should give it no
weight.

## Schema and fixtures

- The JSON Schema ships in the package at
  `model_swap_bench/resources/model-swap-evidence.schema.json`. It is generated
  from the models that write the document, and a test fails if the two drift.
  Every object is closed: an unknown key is an error.
- One fixture per variant the writer can emit is in
  `tests/fixtures/model-swap-evidence/`. A test rebuilds each one through the
  real decision engine and compares it with the committed file.

## Bounds

Strings are at most 256 characters, a document lists at most 16 constraints,
rates are between 0 and 1, and NaN or infinity is refused. A run that falls
outside these bounds is not written; the error names the field and never
repeats the value.
