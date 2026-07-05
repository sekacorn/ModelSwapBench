# Cascade routing

Cascade mode runs a cheap/local model first and escalates only the cases it gets
wrong (or returns invalid JSON for) to a stronger model.

```yaml
cascade:
  first_stage: local-first
  escalation_model: strong-fallback
  conditions: [evaluator_failure, invalid_json, policy_failure, low_score, low_confidence, timeout, case_tag]
  low_score_threshold: 0.5
  low_confidence_threshold: 0.5
  escalate_tags: [complex]
```

## Escalation conditions

| Condition | Triggers when |
|---|---|
| `evaluator_failure` | the case did not fully pass |
| `invalid_json` | output was not valid JSON |
| `policy_failure` | the policy evaluator failed |
| `low_score` | quality score below `low_score_threshold` |
| `low_confidence` | minimum evaluator confidence below `low_confidence_threshold` |
| `timeout` | the first-stage call timed out |
| `case_tag` | the case has a tag in `escalate_tags` |

## Reported economics

`cascade_summary` reports first-stage success rate, escalation rate, final success
rate, combined cost, and combined cost per success — so you can weigh "cheap but
escalates sometimes" against "always use the expensive model." See
`examples/cascade-routing`.
