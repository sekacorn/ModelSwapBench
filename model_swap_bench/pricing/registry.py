"""Versioned, editable pricing registry.

Prices are user-configurable estimates. The registry never claims values are
current; it always surfaces a staleness warning. No internet access is required.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from model_swap_bench.errors import ConfigError

WARNING = "Pricing values are user-configurable estimates and may become outdated."

_DEFAULT_PATH = Path(__file__).resolve().parent / "default_pricing.yaml"


class PricingEntry(BaseModel):
    """A single model's price record (USD per 1,000,000 tokens)."""

    model: str
    provider: str
    input_price: float = 0.0
    output_price: float = 0.0
    currency: str = "USD"
    measured: bool = False
    effective_date: str = ""
    source: str = ""


class PricingRegistry(BaseModel):
    """A collection of :class:`PricingEntry` records with a version."""

    version: str = "0"
    currency: str = "USD"
    entries: list[PricingEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None = None) -> PricingRegistry:
        target = Path(path) if path else _DEFAULT_PATH
        if not target.exists():
            raise ConfigError(f"pricing file not found: {target}")
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)

    def get(self, model: str, provider: str | None = None) -> PricingEntry | None:
        for entry in self.entries:
            if entry.model == model and (provider is None or entry.provider == provider):
                return entry
        return None

    def set_price(self, model: str, provider: str, input_price: float, output_price: float, *, source: str = "") -> PricingEntry:
        existing = self.get(model, provider)
        if existing is not None:
            existing.input_price = input_price
            existing.output_price = output_price
            existing.source = source or existing.source
            existing.measured = False
            return existing
        entry = PricingEntry(model=model, provider=provider, input_price=input_price, output_price=output_price, source=source)
        self.entries.append(entry)
        return entry

    def validate_entries(self) -> list[str]:
        """Return a list of data-quality problems (empty when the registry is clean)."""
        problems: list[str] = []
        seen: set[tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.model, entry.provider)
            if key in seen:
                problems.append(f"duplicate entry for {entry.model} ({entry.provider})")
            seen.add(key)
            if entry.input_price < 0 or entry.output_price < 0:
                problems.append(f"negative price for {entry.model}")
        return problems

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {WARNING}\n" + yaml.safe_dump(self.model_dump(), sort_keys=False), encoding="utf-8")
        return target
