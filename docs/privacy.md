# Privacy and data handling

Benchmark data may contain private business workflows. ModelSwapBench is built to
keep it local.

## Defaults

- Local providers allowed; **hosted providers denied by default**.
- No telemetry, no uploads, no account, no hosted database.
- Raw outputs stored locally under `.modelswapbench/runs/<id>/`.

## Enabling a hosted provider (opt-in)

Both must be true, and you'll see a warning first:

```yaml
privacy:
  allow_hosted_providers: true
```
```bash
modelswapbench run suite.yaml --allow-hosted
```

## Redaction and retention

- `privacy.redact_inputs_in_reports: true` drops raw outputs from stored reports.
- Secrets are redacted from logs and reports; API keys (read from env by name) are
  never written out.
- Mark a case `sensitive: true` to flag confidential content.
- Delete a run (scoped, confirmed): `modelswapbench clean RUN_ID`.

See [provider-trust.md](provider-trust.md) and [../THREAT_MODEL.md](../THREAT_MODEL.md).
