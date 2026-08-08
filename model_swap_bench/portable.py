"""Bounded, deterministic helpers for portable local artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from model_swap_bench.errors import ConfigError, SecurityError

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
MAX_DIAGNOSTIC_CHARS = 4096


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"duplicate key in JSON input: {key!r}")
        result[key] = value
    return result


def read_bounded_text(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES, allow_symlink: bool = False) -> str:
    """Read a local UTF-8 file after enforcing size and symlink limits."""
    if not path.exists() or not path.is_file():
        raise ConfigError(f"input file not found: {path}")
    if path.is_symlink() and not allow_symlink:
        raise SecurityError(f"symbolic-link input is not allowed: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise ConfigError(f"input file exceeds {max_bytes} bytes: {path.name}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"input file must be UTF-8: {path.name}") from exc


def load_json(text: str, *, source: str = "input") -> Any:
    """Parse JSON while rejecting duplicate object keys."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ConfigError:
        raise
    except json.JSONDecodeError as exc:
        raise ConfigError(f"could not parse {source}: {exc}") from exc


def load_json_file(path: Path, *, max_bytes: int = DEFAULT_MAX_BYTES, allow_symlink: bool = False) -> Any:
    return load_json(read_bounded_text(path, max_bytes=max_bytes, allow_symlink=allow_symlink), source=path.name)


def canonical_json(value: Any) -> str:
    """Return stable JSON suitable for hashing and portable artifacts."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bounded_diagnostic(error: object, *, max_chars: int = MAX_DIAGNOSTIC_CHARS) -> str:
    """Bound untrusted parser diagnostics to prevent output flooding."""
    message = str(error)
    return message if len(message) <= max_chars else message[:max_chars] + "... [diagnostic truncated]"


def ensure_distinct_paths(source: Path, destination: Path) -> None:
    """Prevent output from overwriting or aliasing an input path."""
    source_resolved = source.resolve(strict=False)
    destination_resolved = destination.resolve(strict=False)
    if source_resolved == destination_resolved:
        raise SecurityError("output path must not overwrite the input path")
    if destination.is_symlink():
        raise SecurityError(f"symbolic-link output is not allowed: {destination}")
    if source.exists() and destination.exists() and source.samefile(destination):
        raise SecurityError("output path must not alias the input path")
