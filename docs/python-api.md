# Python API

Typed modules are organized by contract: `datasets`, `gates`, `statistics`,
`outcomes`, `workflows`, `replay`, `telemetry`, `privacy`, and
`reports.route_plan`. Imports perform no network activity and return Pydantic
models or deterministic text artifacts.

```python
from pathlib import Path

from model_swap_bench.datasets.io import dataset_digest, load_dataset
from model_swap_bench.gates import evaluate_gate, load_gate_artifact, load_gate_thresholds

dataset = load_dataset(Path("private-evaluation.json"))
print(dataset_digest(dataset))
result = evaluate_gate(
    load_gate_artifact(Path("baseline.json")),
    load_gate_artifact(Path("candidate.json")),
    load_gate_thresholds(Path("gates.json")),
)
```

Portable ecosystem outputs are file contracts, not live integration claims.
