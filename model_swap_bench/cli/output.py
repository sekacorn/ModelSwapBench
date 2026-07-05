"""Console output helpers (Rich) shared across CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from rich.console import Console
from rich.table import Table

# Ensure Unicode output works when stdout/stderr are redirected on Windows (cp1252).
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass

console = Console()
err_console = Console(stderr=True)


def success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def warn(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")


def error(message: str) -> None:
    err_console.print(f"[red]✗[/red] {message}")


def info(message: str) -> None:
    console.print(message)


def table(title: str, columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    """Render a simple table to stdout."""
    tbl = Table(title=title, title_style="bold")
    for col in columns:
        tbl.add_column(col)
    for row in rows:
        tbl.add_row(*[str(c) for c in row])
    console.print(tbl)
