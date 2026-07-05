"""Filesystem artifacts for a run: manifest, full run record, and JSONL results."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from model_swap_bench.results import BenchmarkRun
from model_swap_bench.security.redaction import redact_text, redact_value

MANIFEST_FILE = "manifest.json"
RUN_FILE = "run.json"
RESULTS_FILE = "results.jsonl"


def ensure_run_dirs(run_dir: Path) -> None:
    for sub in ("", "raw", "reports", "logs"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)


def write_run(run_dir: Path, run: BenchmarkRun, manifest: dict[str, Any], *, redact_raw: bool = False) -> None:
    """Persist a run's manifest, full record, and per-case JSONL to ``run_dir``."""
    ensure_run_dirs(run_dir)
    (run_dir / MANIFEST_FILE).write_text(json.dumps(redact_value(manifest), indent=2, default=str) + "\n", encoding="utf-8")

    stored = run.model_copy(deep=True)
    for result in stored.case_results:
        if result.raw_output is not None:
            result.raw_output = redact_text(result.raw_output)
            if redact_raw:
                result.raw_output = None
    (run_dir / RUN_FILE).write_text(stored.model_dump_json(indent=2), encoding="utf-8")
    with (run_dir / RESULTS_FILE).open("w", encoding="utf-8") as handle:
        for result in stored.case_results:
            handle.write(result.model_dump_json() + "\n")


def read_run(run_dir: Path) -> BenchmarkRun:
    """Load a full :class:`BenchmarkRun` from ``run_dir``."""
    return BenchmarkRun.model_validate_json((run_dir / RUN_FILE).read_text(encoding="utf-8"))


def read_manifest(run_dir: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((run_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    return data


def delete_run_dir(run_dir: Path) -> None:
    if run_dir.exists():
        shutil.rmtree(run_dir)
