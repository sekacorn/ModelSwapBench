# Reproducibility

Every run writes a manifest (`.modelswapbench/runs/<id>/manifest.json`) capturing:

- run id, suite name/version, **suite content hash**
- package version, **agentforge-oss (Forge) version**, Python version, platform
- model aliases, provider model ids, endpoints (without secrets)
- execution parameters and seed
- evaluator names, cost mode
- git commit (when available)

A `manifest_hash` over these fields is stored on the run. The full suite is also
snapshotted (`suite.json`) so a run can be re-executed exactly.

## Reproduce a run

```bash
modelswapbench reproduce RUN_ID
```

This re-runs the recorded suite and **warns on version drift** (package, Forge,
Python, or suite hash changed) rather than pretending the new run is identical.

## Determinism notes

- The deterministic provider is fully reproducible.
- Real models (Ollama, OpenAI-compatible) are only as reproducible as the model +
  `seed` allow; ModelSwapBench records the model version actually used.
