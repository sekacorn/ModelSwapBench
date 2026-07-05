from __future__ import annotations

from pathlib import Path

from model_swap_bench.pricing import PricingRegistry


def test_load_default() -> None:
    reg = PricingRegistry.load()
    assert reg.entries
    assert reg.get("qwen2.5:3b") is not None
    assert not reg.validate_entries()


def test_set_and_save(tmp_path: Path) -> None:
    reg = PricingRegistry.load()
    reg.set_price("my-model", "ollama", 1.0, 2.0, source="test")
    entry = reg.get("my-model", "ollama")
    assert entry is not None and entry.input_price == 1.0
    out = tmp_path / "pricing.yaml"
    reg.save(out)
    assert out.exists()
    reloaded = PricingRegistry.load(out)
    assert reloaded.get("my-model") is not None


def test_validate_detects_duplicate() -> None:
    reg = PricingRegistry.load()
    dup = reg.entries[0].model_copy()
    reg.entries.append(dup)
    assert reg.validate_entries()
