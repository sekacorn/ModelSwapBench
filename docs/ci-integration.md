# CI integration

ModelSwapBench is designed to run inside your CI pipeline as a model-regression
gate: run a suite on every change to prompts, models, or workflow code, and fail
the build when constraints regress.

## Exit codes drive the gate

| Code | Meaning |
|---|---|
| 0 | success — all constraints passed |
| 1 | benchmark completed but constraints failed |
| 2 | invalid configuration or input |
| 3 | required provider unavailable |
| 4 | partial / degraded run |
| 5 | internal execution error |

## Example GitHub Actions job (offline / deterministic)

```yaml
jobs:
  model-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: {python-version: "3.13"}
      - run: pip install modelswapbench
      - run: modelswapbench run benchmarks/regression.yaml
      - run: modelswapbench compare latest
      - run: modelswapbench gate evidence/baseline.json evidence/candidate.json --thresholds evidence/gates.json --format github
      - if: always()
        run: modelswapbench report latest --format markdown --output report.md
      - if: always()
        uses: actions/upload-artifact@v5
        with: {name: model-report, path: report.md}
```

Keep the CI suite deterministic (fixtures) or point at a self-hosted runner with a
local Ollama for real-model gates. Never put API keys in benchmark files — use CI
secrets mapped to environment variables named in `api_key_env`.

## Tips

- `--dry-run` validates config + provider health without executing (fast PR check).
- `modelswapbench validate` alone is a cheap lint step for suite files.
- Store `.modelswapbench/` as a build artifact if you want run history per build.

## Evidence gate statuses

`gate` returns `0` only when configured checks pass, `1` for a measured
regression, `2` for invalid artifacts or unsafe paths, and `4` for missing
metrics or too few samples. Formats are `console`, `json`, `markdown`, `github`,
and `junit`; GitHub output uses `GITHUB_STEP_SUMMARY` when present.

A passing gate does not prove generalization. Thresholds inherit dataset bias,
and cost checks inherit the age and accuracy of the declared pricing source.
