# Security Policy

## Reporting a vulnerability

Please report security issues privately via a GitHub security advisory on
[sekacorn/ModelSwapBench](https://github.com/sekacorn/ModelSwapBench/security/advisories)
rather than a public issue. We aim to acknowledge within a few days.

## Security posture

ModelSwapBench is local-first and privacy-preserving by default:

- **No hosted providers by default.** Benchmark data never leaves the machine
  unless you pass `--allow-hosted` **and** set `privacy.allow_hosted_providers`.
- **No telemetry, no auto-upload, no account.**
- **Safe YAML.** Benchmark files are parsed with `yaml.safe_load`; arbitrary Python
  is never executed. No custom-code evaluators in v0.1.
- **Secret hygiene.** API keys are read from environment variables by name and are
  never written to results or reports. Logs and reports are redacted.
- **Path safety.** All run artifacts are written within the storage directory;
  traversal and symlink escapes are blocked. Deletion is scoped and confirmed.
- **Bounded resources.** Concurrency, output size, retries, and timeouts are capped
  to mitigate runaway cost and denial-of-service.
- **Untrusted output.** Model output is treated as untrusted and HTML-escaped in
  reports.

See [THREAT_MODEL.md](THREAT_MODEL.md) for the full analysis.

## Supported versions

v0.1.x (alpha) receives security fixes on a best-effort basis.
