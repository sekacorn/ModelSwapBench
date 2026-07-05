# Scoring

Per case, ModelSwapBench records status, latency, tokens, cost, and each
evaluator's result. These aggregate into a per-model summary.

## Metrics

- **case success** — the case executed and all non-skipped evaluators passed.
- **evaluator pass rate**, **weighted quality score** (mean evaluator score).
- **valid structured-output rate** (over cases with a JSON evaluator).
- **tool-selection accuracy**, **policy pass rate**.
- **latency**: average, median, p95.
- **cost**: total, cost per success (primary — see [cost-per-success.md](cost-per-success.md)).
- **failure / timeout / retry / escalation rates**.

## Transparency

Reports never reduce a model to a single composite score. The quality score is
shown alongside success rate, per-case results, and per-evaluator evidence, so a
failed case is never hidden behind a high average. The replacement engine
explicitly flags a large success-rate drop even when averaged quality stays high.
