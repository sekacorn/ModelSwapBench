# Benchmark format

A benchmark suite is a YAML (or JSON) file validated by typed Pydantic models.
Unknown keys are rejected so typos surface as errors. Print the full JSON Schema
with `modelswapbench schema`.

## Top-level keys

| Key | Meaning |
|---|---|
| `name`, `version`, `description` | Identity of the suite |
| `workflow` | Freeform workflow label |
| `baseline_model` | Alias of the reference model |
| `models` | List of `ModelCandidate` |
| `cases` | List of `BenchmarkCase` |
| `evaluators` | Suite-default evaluators (per-case overrides allowed) |
| `constraints` | Pass/fail gates |
| `scoring` | Cost mode + optional compute profile |
| `execution` | repetitions, concurrency, timeout, retries, seed |
| `cascade` | First-stage + escalation config |
| `privacy` | Hosted-provider permission, redaction |
| `replacement` | Baseline-vs-candidate thresholds |
| `tags`, `metadata` | Freeform |

## ModelCandidate

```yaml
- alias: local-qwen
  provider: ollama            # deterministic | ollama | forge | openai_compatible | openai | anthropic | bedrock
  model: qwen2.5:3b
  deployment: local           # local | self_hosted | hosted | test
  base_url: http://localhost:11434
  estimated_input_cost_per_million: 0
  estimated_output_cost_per_million: 0
  temperature: 0
  seed: 7
  api_key_env: OPENAI_API_KEY # name of the env var, never the key
  fixture: fixtures/local.yaml # deterministic provider only
  metadata: {strategy: oracle} # deterministic provider only
```

## BenchmarkCase

```yaml
- id: duplicate-billing
  description: Customer reports a duplicate charge.
  input: {message: "I was charged twice."}
  expected: {category: billing, escalation_required: true}
  expected_schema: {...}       # optional; else derived from `expected`
  required_fields: [category]
  forbidden_content: ["SSN"]
  required_content: ["refund"]
  expected_tool_calls: [escalate]
  forbidden_tools: [delete_account]
  expected_citations: [policy-1]
  policy: {require_approval: true, forbidden_actions: [delete_account]}
  tags: [billing]
  weight: 1.0
  timeout_override: 30
  evaluators: [json_schema, field_match]   # overrides suite evaluators for this case
  sensitive: false
```

## Evaluator references

An evaluator entry is either a bare string or a mapping with options:

```yaml
evaluators:
  - json_parse
  - {name: field_match, options: {tolerance: 0.01}}
  - {name: citation, options: {allowed: [policy-1, shipping-2]}}
```

`forbidden_content` is an alias for the `contains` evaluator wired to the case's
`forbidden_content` list.
