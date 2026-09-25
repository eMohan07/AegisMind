from __future__ import annotations

import asyncio
import functools
import logging
import random
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def async_retry(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator applying exponential backoff retry with jitter to async functions.

    Formula: delay = min(max_delay, base_delay * (backoff_factor ** attempt))
    With jitter: delay *= uniform(0.8, 1.2)
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except retry_exceptions as exc:
                    last_exc = exc
                    if attempt >= max_retries:
                        logger.error(
                            "Retry exhausted for %s after %d attempts: %s",
                            fn.__name__,
                            attempt + 1,
                            exc,
                        )
                        raise
                    delay = min(max_delay, base_delay * (backoff_factor**attempt))
                    if jitter:
                        delay *= random.uniform(0.8, 1.2)  # noqa: S311
                    logger.warning(
                        "Attempt %d/%d failed for %s (%s). Retrying in %.2fs...",
                        attempt + 1,
                        max_retries,
                        fn.__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
            if last_exc is not None:
                raise last_exc

        return wrapper

    return decorator
