"""Path-safety helpers: prevent traversal and symlink escape when writing runs."""

from __future__ import annotations

import re
from pathlib import Path

from model_swap_bench.errors import SecurityError

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_run_id(run_id: str) -> str:
    """Reject run ids that could be used for path traversal."""
    if ".." in run_id or "/" in run_id or "\\" in run_id or not _RUN_ID_RE.match(run_id):
        raise SecurityError(f"unsafe run id: {run_id!r}")
    return run_id


def resolve_within(base: Path, *parts: str) -> Path:
    """Join ``parts`` under ``base`` and ensure the resolved path stays inside ``base``.

    Guards against ``..`` traversal and symlinks pointing outside the base.
    """
    base_resolved = base.resolve()
    candidate = base_resolved.joinpath(*parts).resolve()
    if base_resolved != candidate and base_resolved not in candidate.parents:
        raise SecurityError(f"path {candidate} escapes base directory {base_resolved}")
    return candidate
