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
