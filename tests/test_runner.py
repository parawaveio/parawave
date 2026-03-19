"""Tests for Runner — single item execution with timeout and retry."""

import asyncio
import time

import pytest

from parawave.hooks import fire_hooks
from parawave.result import ResultItem
from parawave.retry import RetryPolicy
from parawave.runner import run_item


class TestRunItemSuccess:
    async def test_successful_async_function(self):
        async def process(city: str) -> str:
            return f"processed {city}"

        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=None,
            task_timeout=60,
        )
        assert item.ok is True
        assert item.output == "processed NYC"
        assert item.status == "completed"
        assert item.error is None

    async def test_successful_sync_function(self):
        def process(city: str) -> str:
            return f"processed {city}"

        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=False,
            retry_policy=None,
            task_timeout=60,
        )
        assert item.ok is True
        assert item.output == "processed NYC"


class TestRunItemFailure:
    async def test_exception_captured(self):
        async def process(city: str) -> str:
            raise ValueError("bad city")

        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=None,
            task_timeout=60,
        )
        assert item.ok is False
        assert item.status == "failed"
        assert "bad city" in item.error

    async def test_timeout(self):
        async def process(city: str) -> str:
            await asyncio.sleep(10)
            return "done"

        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=None,
            task_timeout=0.05,
        )
        assert item.ok is False
        assert item.status == "failed"
        assert "timeout" in item.error.lower() or "Timeout" in item.error


class TestRunItemRetry:
    async def test_retry_success_on_second_attempt(self):
        attempts = {"n": 0}

        async def process(city: str) -> str:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("transient error")
            return f"processed {city}"

        policy = RetryPolicy(max_retries=2, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=policy,
            task_timeout=60,
        )
        assert item.ok is True
        assert attempts["n"] == 2

    async def test_retry_exhausted(self):
        async def process(city: str) -> str:
            raise ValueError("always fails")

        policy = RetryPolicy(max_retries=2, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=policy,
            task_timeout=60,
        )
        assert item.ok is False
        assert item.status == "failed"

    async def test_non_retryable_exception_skips_retry(self):
        attempts = {"n": 0}

        async def process(city: str) -> str:
            attempts["n"] += 1
            raise TypeError("non-retryable")

        policy = RetryPolicy(
            max_retries=3,
            backoff="fixed",
            base_delay=0.01,
            non_retryable=[TypeError],
        )
        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=policy,
            task_timeout=60,
        )
        assert item.ok is False
        assert attempts["n"] == 1  # no retries

    async def test_on_retry_callback_called(self):
        attempts = {"n": 0}
        retry_calls = {"n": 0}

        async def process(city: str) -> str:
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise ValueError("transient")
            return f"processed {city}"

        async def on_retry():
            retry_calls["n"] += 1

        policy = RetryPolicy(max_retries=3, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=policy,
            task_timeout=60,
            _acquire_rate_token=on_retry,
        )
        assert item.ok is True
        assert item.attempts == 3  # 1 initial + 2 retries
        assert attempts["n"] == 3
        assert retry_calls["n"] == 2  # called before each retry

    async def test_retryable_exception_only(self):
        attempts = {"n": 0}

        async def process(city: str) -> str:
            attempts["n"] += 1
            raise ValueError("retryable")

        policy = RetryPolicy(
            max_retries=2,
            backoff="fixed",
            base_delay=0.01,
            retryable=[ValueError],
        )
        item = await run_item(
            func=process,
            index=0,
            input_data={"city": "NYC"},
            is_async=True,
            retry_policy=policy,
            task_timeout=60,
        )
        assert item.ok is False
        assert attempts["n"] == 3  # 1 initial + 2 retries


class TestRunItemElapsed:
    async def test_successful_item_has_elapsed(self):
        async def slow_fn(x):
            await asyncio.sleep(0.05)
            return x

        item = await run_item(
            func=slow_fn, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=5,
        )
        assert item.elapsed >= 0.04
        assert item.status == "completed"

    async def test_failed_item_has_elapsed(self):
        async def fail_fn(x):
            await asyncio.sleep(0.05)
            raise ValueError("bad")

        item = await run_item(
            func=fail_fn, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=5,
        )
        assert item.elapsed >= 0.04
        assert item.status == "failed"

    async def test_elapsed_includes_retry_time(self):
        call_count = 0

        async def fail_then_succeed(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry me")
            return x

        policy = RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.05)
        item = await run_item(
            func=fail_then_succeed, index=0, input_data={"x": 1},
            is_async=True, retry_policy=policy, task_timeout=5,
        )
        assert item.elapsed >= 0.05
        assert item.status == "completed"
        assert item.attempts == 2


class TestRunItemOutputValidation:
    async def test_non_serializable_output_fails_item(self):
        """Function returning non-JSON-serializable data should fail the item."""
        async def process(x: int):
            return b"binary bytes"

        item = await run_item(
            func=process, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=60,
        )
        assert item.ok is False
        assert item.status == "failed"
        assert "not JSON-serializable" in item.error

    async def test_non_serializable_output_with_retry_exhausts(self):
        """Non-serializable output should exhaust retries since every attempt returns the same type."""
        async def process(x: int):
            return b"binary bytes"

        policy = RetryPolicy(max_retries=2, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=process, index=0, input_data={"x": 1},
            is_async=True, retry_policy=policy, task_timeout=60,
        )
        assert item.ok is False
        assert item.attempts == 3  # 1 initial + 2 retries

    async def test_serializable_output_succeeds(self):
        """JSON-serializable outputs should work as before."""
        async def process(x: int):
            return {"result": x * 2, "tags": ["a", "b"], "value": None}

        item = await run_item(
            func=process, index=0, input_data={"x": 5},
            is_async=True, retry_policy=None, task_timeout=60,
        )
        assert item.ok is True
        assert item.output == {"result": 10, "tags": ["a", "b"], "value": None}

    async def test_non_serializable_output_error_includes_type(self):
        """Error message should include the type name."""
        async def process(x: int):
            return {1, 2, 3}  # set is not serializable

        item = await run_item(
            func=process, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=60,
        )
        assert item.ok is False
        assert "set" in item.error

    async def test_mixed_serializable_and_non_serializable(self):
        """Only items with non-serializable outputs fail; others succeed."""
        async def process(x: int):
            if x == 2:
                return b"binary"
            return x * 10

        item_ok = await run_item(
            func=process, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=60,
        )
        assert item_ok.ok is True
        assert item_ok.output == 10

        item_bad = await run_item(
            func=process, index=1, input_data={"x": 2},
            is_async=True, retry_policy=None, task_timeout=60,
        )
        assert item_bad.ok is False
        assert "not JSON-serializable" in item_bad.error


class TestRunItemOnRetryHooks:
    async def test_on_retry_hooks_called(self):
        call_count = 0
        hook_items = []

        async def fail_then_succeed(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry me")
            return x

        def capture_hook(item):
            hook_items.append(item)

        policy = RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=fail_then_succeed, index=0, input_data={"x": 1},
            is_async=True, retry_policy=policy, task_timeout=5,
            on_retry_hooks=[capture_hook],
        )
        assert item.status == "completed"
        assert len(hook_items) == 1
        assert hook_items[0].status == "failed"
        assert hook_items[0].attempts == 1
        assert hook_items[0].elapsed > 0

    async def test_on_retry_hooks_not_called_on_success(self):
        hook_items = []

        async def succeed(x):
            return x

        def capture_hook(item):
            hook_items.append(item)

        item = await run_item(
            func=succeed, index=0, input_data={"x": 1},
            is_async=True, retry_policy=None, task_timeout=5,
            on_retry_hooks=[capture_hook],
        )
        assert item.status == "completed"
        assert len(hook_items) == 0

    async def test_on_retry_hook_errors_swallowed(self):
        call_count = 0

        async def fail_then_succeed(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("retry me")
            return x

        def bad_hook(item):
            raise RuntimeError("hook exploded")

        policy = RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.01)
        item = await run_item(
            func=fail_then_succeed, index=0, input_data={"x": 1},
            is_async=True, retry_policy=policy, task_timeout=5,
            on_retry_hooks=[bad_hook],
        )
        assert item.status == "completed"
        assert item.attempts == 2
