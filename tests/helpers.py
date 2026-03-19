"""Shared helper factories for integration and unit tests."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------


def make_city_data(n: int) -> list[dict]:
    """Return n dicts with city keys: city_0, city_1, ..."""
    return [{"city": f"city_{i}"} for i in range(n)]


def make_llm_data(n: int) -> list[dict]:
    """Return n dicts suitable for a mock LLM call."""
    return [{"prompt": f"Tell me about topic {i}"} for i in range(n)]


# ---------------------------------------------------------------------------
# Mock LLM helper
# ---------------------------------------------------------------------------


async def mock_llm_call(prompt: str, model: str = "mock-gpt") -> dict:
    """Simulate a fast async LLM call — returns immediately."""
    await asyncio.sleep(0)  # yield to event loop
    return {"prompt": prompt, "model": model, "response": f"Answer for: {prompt}"}


# ---------------------------------------------------------------------------
# Function factories
# ---------------------------------------------------------------------------


def make_fail_n_then_succeed(n: int) -> Callable:
    """Return an async function that raises ValueError for the first *n* calls,
    then succeeds on subsequent calls.

    The returned function is stateful (shared across all calls).
    """
    state = {"calls": 0, "lock": threading.Lock()}

    async def fn(**kwargs) -> str:
        with state["lock"]:
            state["calls"] += 1
            call_n = state["calls"]
        if call_n <= n:
            raise ValueError(f"Transient failure #{call_n}")
        city = kwargs.get("city", "unknown")
        return f"processed {city}"

    return fn


def make_failing_for(failing_keys: set[str]) -> Callable:
    """Return an async function that raises for items whose 'city' is in *failing_keys*."""

    async def fn(**kwargs) -> dict:
        city = kwargs.get("city", "unknown")
        if city in failing_keys:
            raise ValueError(f"Forced failure for {city}")
        return {"city": city, "ok": True}

    return fn


def make_consecutive_failures(n_success: int) -> Callable:
    """Return an async function that succeeds for the first *n_success* calls,
    then always fails — used to trigger stop_on_consecutive_failures.
    """
    state = {"calls": 0, "lock": threading.Lock()}

    async def fn(**kwargs) -> str:
        with state["lock"]:
            state["calls"] += 1
            call_n = state["calls"]
        city = kwargs.get("city", "unknown")
        if call_n <= n_success:
            return f"processed {city}"
        raise ValueError(f"Consecutive failure at call {call_n}")

    return fn


def make_raising(exc_type: type = ValueError, message: str = "always fails") -> Callable:
    """Return an async function that always raises *exc_type*."""

    async def fn(**kwargs) -> str:
        raise exc_type(message)

    return fn


def make_slow(delay: float) -> Callable:
    """Return an async function that sleeps for *delay* seconds."""

    async def fn(**kwargs) -> str:
        await asyncio.sleep(delay)
        city = kwargs.get("city", "unknown")
        return f"processed {city}"

    return fn
