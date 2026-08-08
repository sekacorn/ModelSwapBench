from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_example(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("evidence_driven_example", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evidence_driven_exit_example(tmp_path: Path) -> None:
    script = Path(__file__).parents[2] / "examples" / "evidence-driven-exit" / "run_example.py"
    module = _load_example(script)
    module.main(tmp_path)
    expected = {
        "dataset.jsonl",
        "workflow-evaluation.json",
        "outcome-summary.json",
        "gate-result.json",
        "vendor-exit-plan.md",
        "vendor-exit-plan.json",
        "aimeter-style.json",
        "aiauditlog-style.jsonl",
        "otel.jsonl",
        "sanitized-replay.jsonl",
        "replay-preflight.json",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}
    assert '"status": "pass"' in (tmp_path / "gate-result.json").read_text(encoding="utf-8")
    plan = (tmp_path / "vendor-exit-plan.md").read_text(encoding="utf-8")
    assert "candidate_model" in plan and "human_review" in plan
