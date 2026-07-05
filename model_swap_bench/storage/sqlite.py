"""SQLite index of runs for fast listing and lookup.

Only lightweight, queryable metadata lives here; large artifacts stay on the
filesystem. SQLite is stdlib, file-based, and requires no server — keeping the
tool portable and offline.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    suite_name   TEXT NOT NULL,
    suite_version TEXT NOT NULL,
    mode         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    models       TEXT NOT NULL,
    total_cases  INTEGER NOT NULL,
    constraints_passed INTEGER NOT NULL
);
"""


class RunIndex:
    """A tiny SQLite-backed index of benchmark runs."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(self, row: dict[str, Any]) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO runs (run_id, suite_name, suite_version, mode, created_at, models, total_cases, constraints_passed) "
                "VALUES (:run_id, :suite_name, :suite_version, :mode, :created_at, :models, :total_cases, :constraints_passed) "
                "ON CONFLICT(run_id) DO UPDATE SET suite_name=excluded.suite_name, mode=excluded.mode, "
                "created_at=excluded.created_at, models=excluded.models, total_cases=excluded.total_cases, "
                "constraints_passed=excluded.constraints_passed",
                row,
            )
            conn.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM runs ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def latest(self) -> str | None:
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            return str(row["run_id"]) if row else None

    def delete(self, run_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            conn.commit()
