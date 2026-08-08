# Model Routing Plan

## Executive Summary

Migrate only low-risk candidate-routed tasks first; escalate blocked tasks and review sensitive tasks before any rollout.

## Models Compared

- Baseline model/provider: `openai:gpt-4o`
- Candidate model/provider: `ollama:qwen2.5:3b`
- Date generated: 2026-01-01T00:00:00+00:00
- Benchmark input file or result source: `customer_support_routing_results.json`

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

| Task | Route | Recommendation | Confidence | Samples | Risk | Unknowns | Review |
|---|---|---|---|---:|---|---|---|
| password-reset | `candidate_model` | Recommended replacement | medium | 30 | low | reliability, policy, human_outcome, business_outcome | Not required |
| internal-summary | `candidate_model` | Recommended replacement | medium | 30 | low | reliability, policy, human_outcome, business_outcome | Not required |
| billing-faq | `candidate_model` | Recommended replacement | medium | 30 | medium | reliability, policy, human_outcome, business_outcome | Not required |
| refund-request | `human_review` | Recommended with conditions | medium | 30 | medium | reliability, policy, human_outcome, business_outcome | Required |
| angry-customer-escalation | `human_review` | Recommended with conditions | medium | 30 | high | reliability, policy, human_outcome, business_outcome | Required |
| account-cancellation | `baseline_model` | Not recommended | medium | 30 | medium | reliability, policy, human_outcome, business_outcome | Not required |
| security-concern | `human_review` | Recommended with conditions | medium | 30 | high | reliability, policy, human_outcome, business_outcome | Required |
| legal-question | `blocked_or_escalate` | Blocked pending review | medium | 30 | high | reliability, policy, human_outcome, business_outcome | Required |
| medical-question | `blocked_or_escalate` | Blocked pending review | medium | 30 | high | reliability, policy, human_outcome, business_outcome | Required |
| financial-question | `blocked_or_escalate` | Blocked pending review | medium | 30 | high | cost, reliability, policy, human_outcome, business_outcome | Required |

## Estimated Blended Cost Impact

- Baseline total estimated cost: Unknown
- Candidate-only estimated cost: $6.1000
- Routed/blended estimated cost: Unknown
- Estimated savings vs baseline: Unknown
- Caveat: estimated cost is not invoice-confirmed.
- Caveat: projected savings are not realized savings.

## Risk and Human Review

- `refund-request`: customer-facing
  Evidence: quality 85.56%; cost 82.14%; latency -23.08%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `angry-customer-escalation`: angry; escalated; customer-facing
  Evidence: quality 92.31%; cost 78.13%; latency -14.29%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `account-cancellation`: customer-facing
  Evidence: quality 81.11%; cost 76.92%; latency 76.00%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `security-concern`: security-sensitive
  Evidence: quality 92.47%; cost 77.14%; latency -13.33%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `legal-question`: requires-escalation
  Evidence: quality 93.62%; cost 77.50%; latency -12.50%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `medical-question`: requires-escalation
  Evidence: quality 91.21%; cost 77.50%; latency -9.38%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.
- `financial-question`: requires-escalation; Cost is unknown; missing pricing was not treated as zero.
  Evidence: quality 92.39%; cost Unknown; latency -9.68%.
  Escalation: Escalate to the baseline model and workflow owner.
  Rollback: Rollback on quality, policy, reliability, or business-outcome regression.

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
- Input file path: `customer_support_routing_results.json`
- Run id: `route-plan-example-2026-01-01`
- Package version: 0.1.0a7
- Timestamp: 2026-01-01T00:00:00+00:00
- Python version: 3.13.12
- Platform: Windows-11-10.0.26200-SP0
