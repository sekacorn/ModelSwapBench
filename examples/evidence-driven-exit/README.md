# Evidence-driven vendor-exit example

This offline example creates a private customer-support dataset, deterministic
baseline/candidate evidence, a multi-turn tool workflow, human outcomes,
statistics-backed CI gate, risk-aware route plan, AIMeter-style and
AIAuditLog-style portable files, OpenTelemetry-compatible JSONL, and sanitized
replay artifacts.

```bash
python examples/evidence-driven-exit/run_example.py
```

Outputs go to `evidence-output/`, which is disposable and should not be committed.
The prices are example operator estimates, not invoice-confirmed costs. The
portable files are not live integrations with sibling projects.
