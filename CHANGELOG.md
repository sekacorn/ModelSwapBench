# Changelog

All notable changes to ModelSwapBench are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- **`modelswapbench swap-evidence`** writes a stored run's baseline-versus-
  candidate result as a `model-swap-evidence.v1` document: the run binding,
  each side's provider kind, model and endpoint origin, the summary counts and
  rates, the thresholds, and this package's own verdict. It is the evidence the
  AI Infrastructure Suite's planned `model_providers` vector will read, without
  importing this package. No prompt, output, case id, error text, cost or full
  URL is written. The JSON Schema ships in the package and is generated from
  the models; fixtures cover every variant. See `docs/model-swap-evidence.md`.
  Nothing reads this document yet: the suite's reader is a later release.

## [0.1.0b5] - 2026-11-24

A security release that closes what 0.1.0b4 left open. **If a model's
`base_url` ever carried a token in its query string, rotate it and scrub your
stored runs**: 0.1.0b4 refused `user:password@` but still recorded
`?key=...` in every run artefact. Such a URL is now refused; parameters an
endpoint requires go in the new `default_query`. The `agentforge-oss` floor
also rises to 0.5.5.

### Security
- **A token in a `base_url` query string was written to every run artefact.
  Affects every published version, 0.1.0a1 through 0.1.0b4.** 0.1.0b4 refused
  credentials in a `base_url` (`user:password@host`) but still accepted
  `https://host/v1?key=...`, and recorded that URL in `manifest.json`,
  `run.json`, `results.jsonl` and `suite.json`. A `base_url` with a query
  string or a fragment is now refused when the suite loads, for all three
  providers, with an error that never repeats the URL. **If you ran any
  earlier version with a token in a `base_url`, rotate it** and delete or
  scrub the affected runs under `.modelswapbench/runs/`.
- An unreachable `openai_compatible` endpoint now reports the error type only.
  The HTTP client's error text is no longer stored with each case.
- **Raised the `agentforge-oss` floor to `>=0.5.5,<0.6.0`.** The previous
  floor, `0.5.1`, admitted versions whose provider errors could repeat
  upstream text, including a reflected credential.
- Stored case errors no longer repeat upstream text. An Ollama HTTP error
  stored up to 200 characters of the response body with each case, and the
  `forge` adapter stored the wrapped exception's message. Both now store a
  status code or an exception type. Affects every published version through
  0.1.0b4.

### Added
- **`default_query`** on a model, for query parameters an endpoint requires on
  every request, such as an `api-version`. It is sent by the
  `openai_compatible` provider and refused on the others. Its values are never
  written to a run artefact or a log: every serialization of a model shows
  `[redacted]`, the manifest lists the parameter names only
  (`default_query_params`), and the HTTP client's log lines are redacted.

### Fixed
- `endpoint_is_local` raised on a URL that could not be parsed, such as an
  unclosed IPv6 bracket. It now returns `False`: an endpoint that is not
  positively local is hosted, the same answer AgentForge and the AI
  Infrastructure Suite give.

## [0.1.0b4] - 2026-11-24

A security release. **If you ever put credentials in a model's `base_url`,
rotate them and scrub your stored runs and logs**: every earlier version wrote
that URL, password included, to disk and to the INFO log. Details under
Security. Configurations that supply keys through `api_key_env`, the
documented method, are unaffected and need no change.

### Security
- **A `base_url` containing credentials was written to every run artefact and
  to the logs. Affects every published version, 0.1.0a1 through 0.1.0b3.** A
  model configured with a URL such as `https://user:password@host/v1` was
  accepted and used as given. The endpoint is recorded verbatim in the run's
  `manifest.json`, `run.json`, `results.jsonl` and `suite.json`, and the HTTP
  client logs each request URL at INFO, so the password was stored on disk in
  `.modelswapbench/runs/` and written to any log that captured INFO. When an
  endpoint could not be reached, the error recorded for each case repeated it
  too.

  Such a URL is now refused when the suite loads, with an error that names the
  field and never repeats the URL. Providers check again before sending, for a
  candidate built without validation. Configuration errors no longer copy any
  rejected input into the exception, so a traceback cannot show it either.
  Supply a key through `api_key_env` instead.

  **If you ran any earlier version with credentials in a `base_url`, treat
  them as exposed and rotate them,** and delete or scrub the affected runs
  under `.modelswapbench/runs/` and any logs that captured INFO output.

## [0.1.0b3] - 2026-11-24

A correctness fix for cost and hosting classification. **If you compared a
hosted `openai_compatible` endpoint with no declared pricing on 0.1.0b1 or
0.1.0b2, re-run that comparison**: its cost was reported as `0.0` (free)
instead of unknown, and any ranking or replacement verdict that depended on
cost was computed against that zero. Details under Fixed. No model was ever
run against a hosted endpoint without `--allow-hosted`.

### Fixed
- **Hosted `openai_compatible` endpoints were classified as local, and their
  cost reported as `0.0` instead of unknown.** In 0.1.0b1 and 0.1.0b2, an
  `openai_compatible` model pointed at a hosted endpoint with no declared
  pricing was classified as local, because `deployment` defaults to `local`
  and the provider kind is not in the fixed set of hosted providers. Its cost
  was therefore reported as `0.0` (free) rather than `None` (unknown).
  Replacement scoring treated the same model as deployment-compatible, and
  `msb models` listed it as `local`.

  **Execution was never affected**: the provider classified the endpoint
  itself, and `--allow-hosted` still gated every run against an external one.

  **Impact: re-run any comparison that used a hosted `openai_compatible`
  endpoint without declared pricing.** Its cost figures, and any ranking or
  replacement verdict that depended on them, were computed against a zero
  that should have been unknown.

  Hosting is now derived from the endpoint, by one rule in
  `model_swap_bench.endpoints` that both the configuration and provider
  layers call, so the two can no longer disagree.

### Changed
- A `deployment` declaration can now only **add** hosted-ness. A public
  endpoint is hosted regardless of what `deployment` says, including
  `self_hosted`: whoever owns the server, the content still left the machine.
  Loopback and private-network endpoints are unaffected, declaring `hosted`
  for a local endpoint is still honoured, and a remote `ollama` endpoint is
  now classified as hosted for the same reason.

## [0.1.0b2] - 2026-11-21

### Fixed
- Ollama integration tests no longer probe localhost while pytest imports or
  collects the module. Live contact requires the explicit
  `MODELSWAPBENCH_RUN_OLLAMA_INTEGRATION=1` opt-in and occurs during test setup.
  A regression test asserts that collection performs no network call.

## [0.1.0b1] - 2026-08-13

First Beta. Beta here means the evidence semantics have been hardened so that
unknown or insufficient evidence can no longer masquerade as a favorable result.
It does **not** mean the tool is production-certified, universally safe,
compliance-certified, statistically conclusive, invoice-accurate, or vendor-
independent under every workload.

### Changed (evidence-integrity hardening)
- Unknown cost is now represented explicitly and never treated as zero. Model
  pricing (`estimated_input_cost_per_million` / `estimated_output_cost_per_million`)
  and the derived `CaseResult.estimated_cost_usd` / `ModelSummary.total_cost_usd`
  are now optional: a hosted, per-token-billed model with no declared pricing
  yields an unknown cost (`null`), while a genuinely free local/offline model
  still yields a known `0`. Cost-reduction is `null` whenever baseline or
  candidate cost is unknown — a candidate can no longer appear "100% cheaper" or
  earn an unconditional recommendation because pricing was missing. This also
  fixes the run → AI Vendor Exit Report bridge.
- `ModelSummary.policy_pass_rate` and `valid_json_rate` are now optional and are
  `null` when no policy / JSON-required cases were evaluated (previously `1.0`),
  matching the existing `tool_accuracy` semantics. The replacement decision no
  longer reports a policy pass with zero policy evidence and routes such runs to
  "recommended with conditions"; reports render unevaluated metrics as `n/a`.
- Release workflow pins `pypa/gh-action-pypi-publish` to `v1.14.2`
  (`dc37677b2e1c63e2034f94d8a5b11f265b73ba33`) for Twine 7 / Core Metadata 2.5
  compatibility. Trusted Publishing (GitHub OIDC, `pypi` environment,
  `id-token: write`) is unchanged; no API token is used.

Compatibility: fully specified inputs are unaffected — priced comparisons,
explicit zero-cost local models, policy-evaluated runs, `tool_accuracy`, and the
gate/route-plan/outcome paths behave as before. The only tightening is that
previously misrepresented missing evidence now remains missing.

## [0.1.0a7] - 2026-08-08

### Added
- Strict local JSON/JSONL private datasets with deterministic digests, splits,
  bounded loading, duplicate detection, and redaction.
- Baseline-versus-candidate CI gates with JSON, Markdown, GitHub summary, JUnit
  XML, and stable exit-code outputs.
- Deterministic confidence intervals, distributions, paired comparisons, and
  explicit insufficient-evidence results.
- Pseudonymous human outcomes, complete tool-workflow evaluation, sanitized
  trace replay, OpenTelemetry-compatible JSONL, and privacy preflights.
- Evidence-rich risk-aware routes and a readable static HTML decision report.

### Security
- Reject remote dataset URLs, duplicate JSON keys, oversized inputs, path
  aliases, and symbolic-link artifact inputs or outputs.
- Block hosted execution by default and disclose whether content can leave the
  machine.

### Changed
- Require at least 20 cases before aggregated replacement evidence is treated
  as sufficient by default.

## [0.1.0a7] - 2026-08-06

### Maintenance
- Publish corrected Apache-2.0 package metadata under the public maintainer identity `sekacorn`.

## [0.1.0a5] - 2026-07-21

### Added
- Added `modelswapbench route-plan` for deterministic task-level routing across
  candidate, baseline, human-review, and blocked-or-escalated outcomes.
- Added Markdown and JSON Model Routing Plan outputs with Decimal-safe blended
  cost estimates and explicit unknown-cost handling.
- Added AIMeter OSS-style route cost/outcome JSON and AIAuditLog-style route
  audit-event JSONL exports with optional SHA-256 hash chaining.
- Added deterministic route-plan fixtures, generated examples, documentation,
  and regression tests.

### Fixed
- Enforced workload-level high and regulated risk profiles and required review
  when task risk is unknown.
- Normalized policy/category variants so legal, medical, financial, regulated,
  and security-incident tasks cannot bypass escalation rules through separators.
- Rejected malformed, duplicate, oversized, non-finite, negative, or
  pathological route-plan inputs with stable invalid-input errors.
- Escaped Markdown structure in user-controlled report fields and prevented
  input/output/export path collisions, including existing hard-link aliases.

## [0.1.0a4] - 2026-07-11

### Added
- Added `--export-aimeter` to `modelswapbench exit-report` for Decimal-safe
  AIMeter OSS-style cost/outcome JSON exports.
- Added `--export-auditlog` to `modelswapbench exit-report` for AIAuditLog-style
  JSONL audit events with optional SHA-256 hash-chain fields.
- Added portable export metadata flags for audit events, including `--run-id`,
  `--system-id`, `--actor`, and `--audit-hash-chain/--no-audit-hash-chain`.

### Fixed
- `run --dry-run --allow-hosted` now respects `privacy.allow_hosted_providers`
  before instantiating external providers.
- Running a benchmark with an unknown `--model` alias now fails with a clear
  invalid-input error instead of producing an empty successful run.
- Malformed exit-report JSON or JSONL inputs now produce clean configuration
  errors instead of internal errors.

## [0.1.0a3] - 2026-07-11

### Added
- Added the offline-first AI Vendor Exit Report for baseline-vs-candidate model
  migration decisions.
- Added `modelswapbench exit-report` with Markdown and JSON output formats.
- Added typed exit-report structures and deterministic rule-based decisions for
  quality retention, cost reduction, latency change, operational risk, evidence
  sufficiency, and run reliability.
- Added deterministic vendor-exit example input and sample Markdown report.
- Added documentation for interpreting report metrics, risk profiles, and
  limitations.

### Fixed
- Missing cost data is reported as `Unknown` rather than treated as zero.
- Zero or missing baseline quality is handled without divide-by-zero behavior.
- Exit-report Markdown escapes user-controlled model, workload, and evidence
  fields before rendering.
- Exit-report numeric thresholds reject non-finite and negative values.

## [0.1.0a2] - 2026-07-08

### Release infrastructure
- Reconnected the local `origin` remote to the recreated
  `sekacorn/ModelSwapBench` repository.
- Restricted the PyPI release workflow to version-tag pushes and Trusted
  Publishing through the `pypi` GitHub environment.
- Added release-time verification that the pushed tag matches the package
  version before building distributions.
- Updated project link metadata for the recreated repository.

### Packaging
- Bumped the package version to `0.1.0a2`.
- Reconfirmed the Forge dependency range as `agentforge-oss>=0.5.1,<0.6.0`.

### Documentation
- Documented general PyPI installation separately from editable development
  installation.

## [0.1.0a1] — 2026-07-05

### Added
- First alpha of ModelSwapBench — model portability and replacement benchmark.
- Providers: deterministic (offline), Ollama, Forge adapter (agentforge-oss), OpenAI-compatible (self-hosted).
- Deterministic evaluators: exact_match, contains/forbidden_content, regex, json_parse, json_schema,
  field_match, tool_selection, policy_compliance, citation, latency, cost, and an optional keyword rubric.
- Execution modes: single, comparison, baseline-vs-candidate, and cascade (escalate-on-failure).
- Scoring: success rate, quality, valid-JSON rate, policy pass rate, tool accuracy, latency percentiles,
  and the primary economic metric — cost per successful outcome.
- Transparent, evidence-backed replacement decision engine.
- Local, portable storage (SQLite index + filesystem artifacts) with reproducibility manifests.
- Reports: Markdown, JSON, CSV, and self-contained HTML.
- Editable, versioned pricing registry (offline; estimates only).
- Typer CLI: doctor, init, validate, schema, models, providers, run, compare, report, runs, reproduce,
  clean, pricing, examples.
- Four offline examples: support-ticket-triage, local-rag-citations, code-review-summary, cascade-routing.
