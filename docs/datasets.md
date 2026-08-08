# Private evaluation datasets

Datasets use `modelswapbench.dataset.v1` and remain local. Dataset metadata
contains identity, version, privacy, and provenance. Cases support messages,
references, evaluator settings, rubrics, expected tools, policy and citation
expectations, risk, tags, workload, outcomes, privacy, and a source hash.

```bash
modelswapbench dataset validate dataset.jsonl
modelswapbench dataset inspect dataset.jsonl
modelswapbench dataset digest dataset.jsonl
modelswapbench dataset split dataset.jsonl --train 80 --test 20
modelswapbench dataset redact dataset.jsonl --output dataset.redacted.jsonl
```

Duplicate keys and IDs, oversized content, unknown fields, remote URLs, symbolic
links, and path aliases are rejected. Serialization and digests are stable.
Splits are deterministic by case ID; they do not prove model generalization.
