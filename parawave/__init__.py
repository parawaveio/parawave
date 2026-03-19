"""Parawave — turn any function into a parallel, resilient job.

Usage:
    import parawave

    @parawave(max_concurrency=10)
    async def process(city: str) -> str:
        return call_api(city)

    result = process.run(data=[{"city": "NYC"}, {"city": "LA"}])
"""

import sys
import types

from parawave.decorator import parawave as _parawave_decorator
from parawave.result import Result, ResultItem
from parawave.retry import RetryPolicy
from parawave.state import SharedState
from parawave.storage.base import Storage
from parawave.storage.manager import RunManager

__all__ = [
    "parawave",
    "RetryPolicy",
    "SharedState",
    "RunManager",
    "Result",
    "ResultItem",
    "Storage",
]


class _CallableModule(types.ModuleType):
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            raise TypeError(
                "Use @parawave() with parentheses, not @parawave. "
                "Example: @parawave(max_concurrency=10)"
            )
        return _parawave_decorator(**kwargs)

    # Preserve access to the decorator function directly
    @property
    def parawave(self):
        return _parawave_decorator


sys.modules[__name__].__class__ = _CallableModule
