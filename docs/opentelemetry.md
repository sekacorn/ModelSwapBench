# OpenTelemetry-compatible mapping

`modelswapbench telemetry export` maps workflow JSONL into deterministic records
without requiring an OpenTelemetry SDK.

```bash
modelswapbench telemetry export workflows.jsonl --output otel.jsonl \
  --dataset-id support --dataset-digest SHA256 --run-id RUN_ID
```

The mapping targets evolving GenAI semantic conventions. Records identify the
mapping/schema version and unsupported fields. ModelSwapBench fields remain
explicit for dataset, case, run, risk, route, evaluation, cost, and latency.
Compatibility is not promised to be permanently stable.
