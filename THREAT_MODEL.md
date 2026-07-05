# Threat Model

Scope: ModelSwapBench v0.1 running on a developer/operator machine, benchmarking
local and (optionally) remote models against user-authored benchmark suites.

## Assets

- Private benchmark data (workflow inputs/outputs that may be confidential).
- Provider API keys.
- Integrity of results, decisions, and reports.

## Threats and mitigations

| # | Threat | Mitigation |
|---|---|---|
| 1 | Private benchmark data leaving the machine | Hosted providers denied by default; explicit per-suite opt-in + `--allow-hosted` + warning |
| 2 | API-key leakage | Keys read from env by name; never stored in suites, results, or reports; redaction in logs/reports |
| 3 | Malicious provider response | Output treated as untrusted, size-bounded, HTML-escaped in reports |
| 4 | Prompt injection inside benchmark cases | Cases are data; only field *names* (not values) are shared with models; no tool execution against real systems |
| 5 | Model-output injection into reports | HTML report escapes all dynamic content |
| 6 | Unsafe report rendering | No script execution in HTML; Markdown/JSON/CSV are inert |
| 7 | Path traversal | `security.paths.resolve_within` + `validate_run_id` confine all writes/deletes |
| 8 | Symlink attacks | Paths resolved (`.resolve()`) and checked against the base |
| 9 | Regex denial of service | Regex evaluator caps input size |
| 10 | Unbounded output | Provider responses bounded; raw stored, not executed |
| 11 | Runaway model cost | Budgets, timeouts, retries capped; cost/latency constraints enforced |
| 12 | Excessive concurrency | Hard concurrency ceiling in the scheduler |
| 13 | Provider impersonation | Endpoint classification (local vs external); external needs opt-in |
| 14 | Stale price data | Pricing marked estimate; staleness warning always shown |
| 15 | Manipulated benchmark cases / dishonest evaluator config | Evidence is recorded per case; decisions are transparent, not black-box |
| 16 | Judge-model bias | Rubric evaluator optional, identifies its judge, never the sole evaluator, disabled in deterministic CI |
| 17 | Raw-output retention of sensitive data | Configurable redaction and `store_raw_outputs`; sensitive cases can omit raw I/O |
| 18 | Supply-chain compromise | Pinned CI actions; pip-audit; minimal dependency surface |
| 19 | Malicious YAML / insecure deserialization | `yaml.safe_load` only; strict schema (`extra="forbid"`); no arbitrary objects |

## Non-goals (v0.1)

- Sandboxing untrusted custom evaluator code (not supported — no custom code).
- Multi-tenant isolation or a hosted service.
- Cryptographic signing of manifests (roadmap v0.3).
