"""Regression checks for offline test discovery."""

from __future__ import annotations

import runpy
from pathlib import Path

import httpx
import pytest


def test_importing_ollama_integration_module_does_not_contact_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODELSWAPBENCH_RUN_OLLAMA_INTEGRATION", raising=False)

    def reject_contact(*args: object, **kwargs: object) -> None:
        raise AssertionError("integration module contacted Ollama during import")

    monkeypatch.setattr(httpx, "get", reject_contact)
    module = Path(__file__).parents[1] / "integration" / "test_ollama_integration.py"
    runpy.run_path(str(module), run_name="offline_collection_probe")
