"""Runner — executes a single item with timeout and retry."""

from __future__ import annotations

import asyncio
import json
import time
from parawave.hooks import fire_hooks
from parawave.log import get_logger
from typing import Any, Callable

from parawave.result import ResultItem
from parawave.retry import RetryPolicy

logger = get_logger(__name__)


async def run_item(
    func: Callable,
    index: int,
    input_data: dict,
    is_async: bool,
    retry_policy: RetryPolicy | None,
    task_timeout: float,
    _acquire_rate_token: Callable[[], Any] | None = None,
    on_retry_hooks: list[Callable] | None = None,
) -> ResultItem:
    """Execute a single item, handling timeout and retries.

    Returns a ResultItem with attempts count and elapsed time.
    Never raises — all exceptions are captured.

    Args:
        _acquire_rate_token: Optional async callback called before each retry attempt.
                             Used by the engine to enforce rate limiting on retries.
        on_retry_hooks: Optional list of hook callables fired after each failed attempt
                        (before backoff sleep). Hook errors are swallowed.
    """
    max_attempts = 1 + (retry_policy.max_retries if retry_policy else 0)

    last_error: str | None = None
    attempt_count = 0
    start = time.monotonic()

    for attempt in range(max_attempts):
        attempt_count += 1
        try:
            output = await _invoke(func, input_data, is_async, task_timeout)
            # Validate output is JSON-serializable before returning success
            try:
                json.dumps(output)
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"Output is not JSON-serializable (type: {type(output).__name__}). "
                    f"Return only JSON-serializable values, or save binary data to disk "
                    f"and return a reference."
                ) from exc
            return ResultItem(
                index=index,
                input=input_data,
                output=output,
                status="completed",
                error=None,
                attempts=attempt_count,
                elapsed=time.monotonic() - start,
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            is_last_attempt = attempt == max_attempts - 1

            if is_last_attempt:
                break

            # Check if we should retry
            if retry_policy and not retry_policy.should_retry(exc):
                logger.debug(
                    "Item %d: %s is non-retryable, skipping retry",
                    index,
                    type(exc).__name__,
                )
                break

            # Fire on_retry hooks after failed attempt
            if on_retry_hooks:
                retry_item = ResultItem(
                    index=index, input=input_data, output=None,
                    status="failed", error=last_error, attempts=attempt_count,
                    elapsed=time.monotonic() - start,
                )
                fire_hooks(on_retry_hooks, retry_item)

            delay = retry_policy.get_delay(attempt) if retry_policy else 0
            logger.debug(
                "Item %d: attempt %d/%d failed (%s), retrying in %.2fs",
                index,
                attempt,
                max_attempts,
                last_error,
                delay,
            )
            await asyncio.sleep(delay)

            # Rate limit callback before retry (spec: retries consume tokens)
            if _acquire_rate_token is not None:
                await _acquire_rate_token()

    return ResultItem(
        index=index,
        input=input_data,
        output=None,
        status="failed",
        error=last_error,
        attempts=attempt_count,
        elapsed=time.monotonic() - start,
    )


async def _invoke(
    func: Callable, input_data: dict, is_async: bool, timeout: float
) -> Any:
    """Invoke the user function with timeout."""
    if is_async:
        coro = func(**input_data)
    else:
        coro = asyncio.to_thread(func, **input_data)
    return await asyncio.wait_for(coro, timeout=timeout)
