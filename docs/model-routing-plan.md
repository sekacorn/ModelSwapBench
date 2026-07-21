# Model Routing Plan

The Model Routing Plan is a deterministic, offline-first report for gradual
model migration. Instead of asking only whether a candidate model can replace a
baseline model for an entire workload, it asks which individual tasks can move
now, which need human review, which should stay on the baseline, and which
should be blocked or escalated.

This is more realistic than all-or-nothing migration because many workloads mix
routine internal tasks with customer-facing, regulated, safety-sensitive, or
insufficiently evaluated tasks.

## Example

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

## Inputs

The input is JSON with workload metadata and a `tasks` list. Each task can
include:

- task id and category;
- risk level;
- baseline and candidate quality scores;
- baseline and candidate latency;
- baseline and candidate estimated cost;
- policy flags;
- failure flags;
- notes.

Missing cost remains unknown. It is never treated as zero.

Input is limited to 10 MiB and 10,000 tasks. Task ids must be unique, and
scores, costs, and latencies must be finite, non-negative values within the
documented parser bounds. Duplicate JSON object keys are rejected.

## Outputs

The Markdown report includes:

- Executive Summary;
- Models Compared;
- Workload;
- Routing Summary;
- Task Routing Table;
- Estimated Blended Cost Impact;
- Risk and Human Review;
- Recommendation;
- Limitations;
- Reproducibility.

The JSON output is deterministic and parseable. It includes the same plan
payload, thresholds, task decisions, routing percentages, and cost impact.

## Decision Logic

Tasks can be routed to:

- `candidate_model`: quality, risk, latency, and cost evidence support candidate
  routing.
- `baseline_model`: quality fails, candidate failure flags exist, latency is
  unacceptable, or baseline routing is safer.
- `human_review`: the candidate may be usable but risk, sensitivity, customer
  impact, borderline quality, weak cost reduction, or unknown evidence requires
  review.
- `blocked_or_escalate`: the task is blocked, regulated, explicitly escalated,
  safety-critical, legal, medical, financial, security-incident related, or
  insufficiently evaluated.

Default thresholds:

- minimum quality retention: 80%;
- maximum latency increase: 50%;
- minimum cost reduction: 20%;
- high risk requires review: true.

The workload-level risk profile is also enforced: `high` prevents direct
candidate routing, while `regulated` blocks or escalates tasks. Tasks whose
individual risk level is unknown require human review.

## Portable Exports

`--export-aimeter` writes an AIMeter OSS-style JSON summary with baseline total
estimated cost, candidate-only estimated cost, routed/blended estimated cost,
estimated savings versus baseline when calculable, route counts, quality outcome
summary, and limitations.

`--export-auditlog` writes AIAuditLog-style JSONL events for route-plan start,
input load, threshold evaluation, per-task route decisions, route-plan
generation, and optional AIMeter route export generation.

These exports are portable file examples. They are not deep runtime integrations
with AIMeter OSS or AIAuditLog.

## Limitations

- Estimated cost is not invoice-confirmed.
- Projected savings are not realized savings.
- Blended cost uses baseline model cost as a conservative proxy for tasks sent
  to baseline, review, or escalation; human-review and escalation labor costs
  are not included.
- Route decisions are not legal, regulatory, safety, security, or compliance
  guarantees.
- Human review may be required.
- Model behavior can change across versions, providers, prompts, and runtime
  environments.
- Benchmark results do not prove universal safety.
- Hash chaining, when present in audit events, is tamper-evident style evidence,
  not immutable storage.
- Audit events do not prove legal non-repudiation.
