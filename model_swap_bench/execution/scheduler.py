"""Bounded-concurrency scheduling for async tasks.

Concurrency is capped to protect local machines and avoid runaway parallel model
calls — a safety requirement from the threat model.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

#: Hard ceiling on concurrency regardless of user configuration.
MAX_CONCURRENCY = 32


async def run_bounded(factories: Sequence[Callable[[], Awaitable[T]]], concurrency: int) -> list[T]:
    """Run task factories with at most ``concurrency`` in flight; preserve input order."""
    limit = max(1, min(concurrency, MAX_CONCURRENCY))
    semaphore = asyncio.Semaphore(limit)

    async def _guarded(factory: Callable[[], Awaitable[T]]) -> T:
        async with semaphore:
            return await factory()

    return await asyncio.gather(*[_guarded(f) for f in factories])
