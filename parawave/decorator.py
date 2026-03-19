"""The @parawave() decorator."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from parawave.errors import ValidationError
from parawave.process import Process
from parawave.retry import RetryPolicy


def parawave(
    max_concurrency: int = 10,
    rate_limit: int | None = None,
    rate_period: float = 1,
    retry: RetryPolicy | None = None,
    executor: str = "auto",
    task_timeout: float = 60,
    run_timeout: float | None = None,
    stop_on_consecutive_failures: int | None = None,
    storage: str = "in_memory",
    progress: str | None | Any = "console",
    on_start: list[Callable] | None = None,
    on_retry: list[Callable] | None = None,
    on_item_complete: list[Callable] | None = None,
    on_item_error: list[Callable] | None = None,
    on_complete: list[Callable] | None = None,
    warmup: bool = False,
) -> Callable:
    """Decorator that wraps a function into a parawave Process."""

    # Validate parameter ranges at decoration time
    if max_concurrency < 1:
        raise ValidationError("max_concurrency must be >= 1")
    if task_timeout <= 0:
        raise ValidationError("task_timeout must be > 0")
    if run_timeout is not None and run_timeout <= 0:
        raise ValidationError("run_timeout must be > 0")
    if rate_limit is not None and rate_limit <= 0:
        raise ValidationError("rate_limit must be > 0")
    if rate_period <= 0:
        raise ValidationError("rate_period must be > 0")
    if stop_on_consecutive_failures is not None and stop_on_consecutive_failures < 1:
        raise ValidationError("stop_on_consecutive_failures must be >= 1")
    def decorator(func: Callable) -> Process:
        is_async = inspect.iscoroutinefunction(func)

        if executor == "async" and not is_async:
            raise ValidationError(
                'executor="async" requires an async function'
            )
        if executor == "thread" and is_async:
            raise ValidationError(
                'executor="thread" requires a sync function'
            )

        config = {
            "max_concurrency": max_concurrency,
            "rate_limit": rate_limit,
            "rate_period": rate_period,
            "retry": retry,
            "executor": executor,
            "task_timeout": task_timeout,
            "run_timeout": run_timeout,
            "stop_on_consecutive_failures": stop_on_consecutive_failures,
            "storage": storage,
            "progress": progress,
            "on_start": on_start or [],
            "on_retry": on_retry or [],
            "on_item_complete": on_item_complete or [],
            "on_item_error": on_item_error or [],
            "on_complete": on_complete or [],
            "warmup": warmup,
        }

        return Process(func=func, config=config)

    return decorator
