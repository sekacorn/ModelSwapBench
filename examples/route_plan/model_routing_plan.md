# Model Routing Plan

## Executive Summary

Migrate only low-risk candidate-routed tasks first; escalate blocked tasks and review sensitive tasks before any rollout.

## Models Compared

- Baseline model/provider: `openai:gpt-4o`
- Candidate model/provider: `ollama:qwen2.5:3b`
- Date generated: 2026-01-01T00:00:00+00:00
- Benchmark input file or result source: `examples\route_plan\customer_support_routing_results.json`

## Workload

- Workload name: Customer support routing
- Risk profile: medium
- Task count: 10

## Routing Summary

- Candidate model: 30.00% of tasks
- Baseline model: 10.00% of tasks
- Human review: 30.00% of tasks
- Blocked/escalate: 30.00% of tasks
- Estimated blended savings: Unknown

## Task Routing Table

| Task | Category | Route | Risk | Quality | Cost | Latency | Reason |
|---|---|---|---|---:|---:|---:|---|
| password-reset | account-help | `candidate_model` | low | 94.74% | 87.50% | -25.00% | Quality, risk, latency, and cost evidence support candidate routing. |
| internal-summary | internal-summary | `candidate_model` | low | 94.62% | 88.89% | -25.00% | Quality, risk, latency, and cost evidence support candidate routing. |
| billing-faq | billing-faq | `candidate_model` | medium | 91.30% | 83.33% | -13.64% | Quality, risk, latency, and cost evidence support candidate routing. |
| refund-request | refund-request | `human_review` | medium | 85.56% | 82.14% | -23.08% | Candidate may be usable, but risk, sensitivity, or borderline evidence requires review. |
| angry-customer-escalation | escalation | `human_review` | high | 92.31% | 78.13% | -14.29% | Candidate may be usable, but risk, sensitivity, or borderline evidence requires review. |
| account-cancellation | account-cancellation | `baseline_model` | medium | 81.11% | 76.92% | 76.00% | Candidate has failure flags that make baseline routing safer. |
| security-concern | security-concern | `human_review` | high | 92.47% | 77.14% | -13.33% | Candidate may be usable, but risk, sensitivity, or borderline evidence requires review. |
| legal-question | legal | `blocked_or_escalate` | high | 93.62% | 77.50% | -12.50% | Task is blocked, regulated, escalated, or insufficiently evaluated. |
| medical-question | medical | `blocked_or_escalate` | high | 91.21% | 77.50% | -9.38% | Task is blocked, regulated, escalated, or insufficiently evaluated. |
| financial-question | financial | `blocked_or_escalate` | high | 92.39% | Unknown | -9.68% | Task is blocked, regulated, escalated, or insufficiently evaluated. |

## Estimated Blended Cost Impact

- Baseline total estimated cost: Unknown
- Candidate-only estimated cost: $6.1000
- Routed/blended estimated cost: Unknown
- Estimated savings vs baseline: Unknown
- Caveat: estimated cost is not invoice-confirmed.
- Caveat: projected savings are not realized savings.

## Risk and Human Review

- `refund-request`: customer-facing
- `angry-customer-escalation`: angry; escalated; customer-facing
- `account-cancellation`: customer-facing
- `security-concern`: security-sensitive
- `legal-question`: requires-escalation
- `medical-question`: requires-escalation
- `financial-question`: requires-escalation; Cost is unknown; missing pricing was not treated as zero.

## Recommendation

Migrate only low-risk candidate-routed tasks first; escalate blocked tasks and review sensitive tasks before any rollout.

## Limitations

- This plan is based on benchmark inputs and rule-based thresholds.
- Estimated cost is not invoice-confirmed.
- Projected savings are not realized savings.
- Blended cost uses baseline model cost as a proxy for review and escalation routes; human labor cost is excluded.
- Route decisions are not legal, regulatory, safety, security, or compliance guarantees.
- Human review may be required for high-risk or sensitive workflows.
- Model behavior can change across versions, providers, prompts, and runtime environments.
- Benchmark results do not prove universal safety.
- AIMeter and AIAuditLog outputs are portable file exports, not live runtime integrations.

## Reproducibility

- CLI command used: `modelswapbench route-plan --input examples\route_plan\customer_support_routing_results.json --output examples\route_plan\model_routing_plan.md --format markdown --export-json examples\route_plan\model_routing_plan.json --export-aimeter examples\route_plan\aimeter_route_summary.json --export-auditlog examples\route_plan\route_audit_events.jsonl`
- Input file path: `examples\route_plan\customer_support_routing_results.json`
- Run id: `route-plan-example-2026-01-01`
- Package version: 0.1.0a5
- Timestamp: 2026-01-01T00:00:00+00:00
- Python version: 3.13.12
- Platform: Windows-11-10.0.26200-SP0
