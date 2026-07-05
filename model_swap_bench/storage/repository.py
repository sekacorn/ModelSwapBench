"""High-level run repository combining the SQLite index and filesystem artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from model_swap_bench.config.models import BenchmarkSuite
from model_swap_bench.errors import StorageError
from model_swap_bench.results import BenchmarkRun
from model_swap_bench.security.paths import resolve_within, validate_run_id
from model_swap_bench.storage import files
from model_swap_bench.storage.manifests import build_manifest
from model_swap_bench.storage.sqlite import RunIndex

STORAGE_DIRNAME = ".modelswapbench"
LATEST = "latest"


class RunRepository:
    """Store, list, load, and delete benchmark runs under ``<root>/.modelswapbench``."""

    def __init__(self, root: str | Path = ".") -> None:
        self.base = Path(root).resolve() / STORAGE_DIRNAME
        self.runs_dir = self.base / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.index = RunIndex(self.base / "index.sqlite")

    def run_dir(self, run_id: str) -> Path:
        validate_run_id(run_id)
        return resolve_within(self.runs_dir, run_id)

    def reports_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "reports"

    def resolve(self, run_ref: str) -> str:
        """Resolve ``latest`` (or a real id) to a concrete run id."""
        if run_ref == LATEST:
            latest = self.index.latest()
            if latest is None:
                raise StorageError("no runs found; run a benchmark first")
            return latest
        return validate_run_id(run_ref)

    def save(self, run: BenchmarkRun, suite: BenchmarkSuite, *, suite_dir: Path | None = None) -> Path:
        run_dir = self.run_dir(run.run_id)
        manifest = build_manifest(suite, run.run_id, suite_dir)
        files.write_run(run_dir, run, manifest, redact_raw=suite.privacy.redact_inputs_in_reports)
        (run_dir / "suite.json").write_text(suite.model_dump_json(indent=2), encoding="utf-8")
        self.index.upsert(
            {
                "run_id": run.run_id,
                "suite_name": run.suite_name,
                "suite_version": run.suite_version,
                "mode": run.mode,
                "created_at": run.created_at.isoformat(),
                "models": json.dumps([m.model_alias for m in run.model_summaries]),
                "total_cases": len(run.case_results),
                "constraints_passed": int(run.all_constraints_passed),
            }
        )
        return run_dir

    def load(self, run_ref: str) -> BenchmarkRun:
        run_id = self.resolve(run_ref)
        run_dir = self.run_dir(run_id)
        if not (run_dir / files.RUN_FILE).exists():
            raise StorageError(f"run {run_id!r} not found in {self.runs_dir}")
        return files.read_run(run_dir)

    def load_suite_snapshot(self, run_ref: str) -> BenchmarkSuite:
        run_id = self.resolve(run_ref)
        snapshot = self.run_dir(run_id) / "suite.json"
        if not snapshot.exists():
            raise StorageError(f"no suite snapshot stored for run {run_id!r}; cannot reproduce")
        return BenchmarkSuite.model_validate_json(snapshot.read_text(encoding="utf-8"))

    def load_manifest(self, run_ref: str) -> dict[str, object]:
        run_id = self.resolve(run_ref)
        return files.read_manifest(self.run_dir(run_id))

    def list_runs(self) -> list[dict[str, object]]:
        return self.index.list_runs()

    def latest(self) -> str | None:
        return self.index.latest()

    def delete(self, run_ref: str) -> str:
        run_id = self.resolve(run_ref)
        files.delete_run_dir(self.run_dir(run_id))
        self.index.delete(run_id)
        return run_id
