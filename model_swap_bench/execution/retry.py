"""Bounded retry with a simple backoff for transient provider failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from model_swap_bench.errors import ProviderError, ProviderUnavailableError
from model_swap_bench.providers.base import ProviderResponse

T = TypeVar("T")


class RetryOutcome:
    """Records how many retries were consumed reaching a result."""

    def __init__(self) -> None:
        self.retries = 0


async def call_with_retry(
    func: Callable[[], Awaitable[ProviderResponse]],
    *,
    retries: int,
    outcome: RetryOutcome,
    backoff_seconds: float = 0.0,
) -> ProviderResponse:
    """Call ``func`` up to ``retries`` extra times on retryable provider errors.

    ``ProviderUnavailableError`` is never retried — a missing endpoint/model will
    not fix itself within a run.
    """
    attempt = 0
    last_exc: ProviderError | None = None
    while attempt <= retries:
        try:
            return await func()
        except ProviderUnavailableError:
            raise
        except ProviderError as exc:
            last_exc = exc
            if attempt == retries:
                break
            outcome.retries += 1
            attempt += 1
            if backoff_seconds > 0:
                await asyncio.sleep(backoff_seconds)
    assert last_exc is not None
    raise last_exc
