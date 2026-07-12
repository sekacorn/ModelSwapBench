# AI Vendor Exit Report

The AI Vendor Exit Report turns benchmark summaries into a plain-English
replacement decision for a baseline model and a candidate model. It is designed
for offline, deterministic evidence first: users can generate reports from
fixture JSON, JSONL rows, or exported ModelSwapBench result summaries without
calling a hosted provider.

Example:

```bash
modelswapbench exit-report \
  --baseline openai:gpt-4o \
  --candidate ollama:qwen2.5:3b \
  --input examples/vendor_exit/customer_support_results.json \
  --output reports/vendor_exit_report.md \
  --format markdown \
  --risk-profile medium
```

The report includes quality retention, estimated cost reduction, latency change,
operational risk, a rule-based decision, limitations, and reproducibility facts.

Cost values are estimates, not invoice-confirmed costs. Missing pricing is
reported as unknown and is never treated as zero.

## Portable exports

`modelswapbench exit-report` can also write portable, offline-first files for
adjacent Linux of AI workflows:

- `--export-aimeter PATH` writes an AIMeter OSS-style JSON summary that carries
  estimated cost, usage-adjacent efficiency, latency, and outcome data into
  cost/outcome measurement workflows.
- `--export-auditlog PATH` writes AIAuditLog-style JSONL events that carry the
  model-migration decision into portable audit evidence workflows.

Example:

```bash
modelswapbench exit-report \
  --baseline hosted-example:premium-model \
  --candidate local-example:local-small-model \
  --input examples/vendor_exit/customer_support_results.json \
  --output reports/ai_vendor_exit_report.md \
  --format markdown \
  --export-aimeter reports/aimeter_summary.json \
  --export-auditlog reports/audit_events.jsonl
```

Optional audit metadata flags include `--run-id`, `--system-id`, `--actor`, and
`--audit-hash-chain/--no-audit-hash-chain`. Hash chaining is intended for
tamper-evident review only; it is not immutable storage.

Limitations:

- These are file-based export formats, not deep runtime integrations.
- Estimated cost is not invoice-confirmed.
- Projected savings are not realized savings.
- Audit events do not prove legal non-repudiation.
- The exports do not prove legal, regulatory, safety, security, or operational
  compliance.
- Human review may be required in high-risk workflows.
