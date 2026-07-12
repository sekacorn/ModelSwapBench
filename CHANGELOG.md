# Changelog

All notable changes to ModelSwapBench are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
