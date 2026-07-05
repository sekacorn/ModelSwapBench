# Changelog

All notable changes to ModelSwapBench are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
