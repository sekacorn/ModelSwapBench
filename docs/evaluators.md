# Evaluators

Evaluators are deterministic by default and always return an explanation plus
evidence — never a bare pass/fail. Each produces a score in `[0, 1]`, a weight,
and a confidence.

| Evaluator | Checks |
|---|---|
| `exact_match` | Output equals `expected_text` (optional whitespace/case normalization) |
| `contains` | Required substrings present, forbidden absent |
| `forbidden_content` | Alias of `contains` wired to the case's `forbidden_content` |
| `regex` | Pattern matches / forbidden pattern absent (input size bounded) |
| `json_parse` | Output is valid JSON (populates parsed output for others) |
| `json_schema` | Validates against `expected_schema`, or a schema derived from `expected` |
| `field_match` | Compares fields: exact, numeric tolerance, list membership, normalized strings |
| `tool_selection` | Expected tools called (optional order), forbidden tools not called |
| `policy_compliance` | Forbidden actions not taken; required refusal/approval; required events recorded |
| `citation` | Required source ids cited; no unsupported (fabricated) citation |
| `latency` | Case latency within budget |
| `cost` | Case estimated cost within budget |
| `rubric` | Optional keyword heuristic (offline) or judge mode (roadmap) |

## Evaluation order

`json_parse` populates parsed output, but `json_schema` and `field_match` also parse
lazily on demand, so ordering is not fragile.

## The rubric evaluator

The model-assisted rubric is **optional**, must identify its judge, is **never the
sole evaluator**, and is disabled in deterministic CI. In v0.1 it supports a
deterministic `keyword` mode (labeled a heuristic, not ground truth); without a
configured judge it skips rather than fabricating a score. See
[docs/adding-an-evaluator.md](adding-an-evaluator.md) to add your own.
