"""Run manifests for reproducibility.

A manifest captures everything needed to understand and re-run a benchmark:
suite hash, tool versions, environment, model/provider identities (without
secrets), and execution parameters.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from model_swap_bench._version import __version__
from model_swap_bench.config.models import BenchmarkSuite


def _forge_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("agentforge-oss")
    except Exception:  # noqa: BLE001 - version discovery is best-effort
        return "unknown"


def _git_commit(suite_dir: Path | None) -> str | None:
    cwd = suite_dir if suite_dir and suite_dir.exists() else Path.cwd()
    git = shutil.which("git")
    if git is None:
        return None
    try:
        # The executable and arguments are fixed; only the working directory varies.
        out = subprocess.run(  # noqa: S603  # nosec B603
            [git, "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def suite_content_hash(suite: BenchmarkSuite) -> str:
    """Stable hash of the normalized suite definition."""
    payload = suite.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest(suite: BenchmarkSuite, run_id: str, suite_dir: Path | None = None) -> dict[str, Any]:
    """Assemble a reproducibility manifest for a run."""
    return {
        "run_id": run_id,
        "suite_name": suite.name,
        "suite_version": suite.version,
        "suite_hash": suite_content_hash(suite),
        "package_version": __version__,
        "forge_version": _forge_version(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "models": [
            {
                "alias": m.alias,
                "provider": m.provider.value,
                "model": m.model,
                "deployment": m.deployment.value,
                "endpoint": m.base_url,  # never contains a secret
            }
            for m in suite.models
        ],
        "execution": suite.execution.model_dump(mode="json"),
        "seed": suite.execution.seed,
        "cost_mode": suite.scoring.cost_mode.value,
        "evaluators": sorted({s.name for s in suite.evaluators} | {s.name for c in suite.cases for s in c.evaluators}),
        "git_commit": _git_commit(suite_dir),
    }


def manifest_hash(manifest: dict[str, Any]) -> str:
    """Deterministic hash of a manifest (sorted keys)."""
    payload = json.dumps(manifest, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
