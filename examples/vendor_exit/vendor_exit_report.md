# AI Vendor Exit Report

## Executive Summary

Candidate acceptable. Use candidate model for low-risk internal workflows and monitor drift.

## Models Compared

- Baseline model/provider: `openai:gpt-4o` (openai:gpt-4o)
- Candidate model/provider: `ollama:qwen2.5:3b` (ollama:qwen2.5:3b)
- Workload name: Customer support triage
- Date generated: 2026-08-05T09:10:28.485713+00:00
- Benchmark input file or result source: `examples\vendor_exit\customer_support_results.json`

## Decision

**Candidate acceptable**

Reasons:
- Candidate failures or reliability regression require review.
- Quality, cost, latency, and risk gates passed.

## Quality

- Baseline score: 0.92
- Candidate score: 0.84
- Quality retention: 91.30%
- Threshold used: 80.00%
- Result: PASS

## Cost

- Baseline estimated cost: $24.0000
- Candidate estimated cost: $3.2000
- Estimated cost difference: $-20.8000
- Estimated cost reduction: 86.67%
- Caveat: estimated cost is not invoice-confirmed.
- Caveat: projected savings are not realized savings.
- Result: PASS

## Latency

- Baseline average latency: 1250.00 ms
- Candidate average latency: 980.00 ms
- Latency delta: -21.60%
- Threshold used: 50.00% maximum increase
- Result: PASS

## Risk

- Risk profile: medium
- Operational risk level: Medium
- Reason: Candidate failures or reliability regression require review.
- Recommended use boundaries: start with bounded workflows, monitor drift, and keep rollback paths available.

## Recommendation

Use candidate model for low-risk internal workflows and monitor drift.

## Limitations

- This report is based on benchmark inputs and scoring configuration.
- Estimated cost is not invoice-confirmed.
- Projected savings are not realized savings.
- Passing this benchmark does not prove legal, regulatory, safety, or security compliance.
- Human review may still be required for high-risk workflows.
- Model behavior can change across versions, providers, prompts, and runtime environments.

## Reproducibility

- CLI command used: `modelswapbench exit-report --baseline openai:gpt-4o --candidate ollama:qwen2.5:3b --input examples\vendor_exit\customer_support_results.json --output examples\vendor_exit\vendor_exit_report.md --format markdown`
- Input file path: `examples\vendor_exit\customer_support_results.json`
- Package version: 0.1.0b1
- Timestamp: 2026-08-05T09:10:28.485713+00:00
- Python version: 3.13.12
- Platform: Windows-11-10.0.26200-SP0
