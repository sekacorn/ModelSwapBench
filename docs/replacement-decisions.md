# Replacement decisions

The replacement engine is transparent and rules-based. A candidate is recommended
only when **every** required gate passes, and the decision always carries its
evidence.

## Possible outcomes

- **recommended replacement**
- **recommended with conditions** (quality/reliability fine, target cost reduction not demonstrated)
- **suitable as first-stage model with escalation** (fails direct, but a cascade recovers it)
- **not recommended**
- **insufficient evidence** (too few / all-error cases)

## Gates evaluated

- quality drop vs baseline ≤ `maximum_quality_drop`
- **success-rate drop** ≤ `maximum_quality_drop` (a failed case is never hidden by a high average)
- cost reduction ≥ `minimum_cost_reduction` (when cost is quantifiable)
- p95 latency ≤ `maximum_latency_ms` (if set)
- success rate ≥ `minimum_reliability` (if set)
- policy pass rate = 100%
- deployment compatible (hosted candidate requires hosted permission)
- all suite constraints pass

## Example

```
Candidate: local-candidate
Decision: recommended replacement (confidence 90%)
Evidence:
  - 100% direct success (5/5)
  - quality 1.00 vs baseline 1.00 (drop 0.00)
  - 100% cost reduction vs baseline
Next step: pilot on a slice of production traffic and monitor quality/cost.
```

Failures are listed explicitly (`failed_constraints`) and never obscured. Low case
counts reduce the reported confidence.
