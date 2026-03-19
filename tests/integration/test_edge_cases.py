"""Integration tests — failure injection, edge cases, stress."""

import asyncio

import pytest

import parawave
from parawave import RetryPolicy
from parawave.errors import ValidationError
from tests.helpers import (
    make_consecutive_failures,
    make_failing_for,
    make_raising,
    make_slow,
    make_city_data,
)


class TestAllItemsFail:
    def test_all_fail_returns_result(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str) -> str:
            raise ValueError("everything is broken")

        result = process.run(data=make_city_data(5))
        assert result.ok is False
        assert len(result.failed) == 5
        assert len(result.completed) == 0


class TestPartialFailure:
    def test_specific_inputs_fail(self):
        fn = make_failing_for({"city_1", "city_3"})

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def process(city: str) -> dict:
            return await fn(city=city)

        result = process.run(data=make_city_data(5))
        assert result.ok is False
        assert len(result.completed) == 3
        assert len(result.failed) == 2
        assert result[1].ok is False
        assert result[3].ok is False


class TestTimeout:
    def test_slow_items_timeout(self):
        fn = make_slow(5.0)  # 5 seconds, way over timeout

        @parawave(
            task_timeout=0.1, storage="in_memory", progress=None
        )
        async def process(city: str) -> str:
            return await fn(city=city)

        result = process.run(data=[{"city": "NYC"}])
        assert result.ok is False
        assert result[0].status == "failed"


class TestStopOnConsecutiveFailures:
    def test_stops_early(self):
        fn = make_consecutive_failures(3)

        @parawave(
            max_concurrency=1,
            stop_on_consecutive_failures=3,
            storage="in_memory",
            progress=None,
        )
        async def process(city: str) -> str:
            return await fn(city=city)

        result = process.run(data=make_city_data(20))
        assert result.ok is False
        assert len(result.completed) == 3
        assert len(result.pending) > 0


class TestExceptionFiltering:
    def test_non_retryable_exception(self):
        calls = {"n": 0}

        @parawave(
            retry=RetryPolicy(
                max_retries=3,
                backoff="fixed",
                base_delay=0.01,
                non_retryable=[TypeError],
            ),
            storage="in_memory",
            progress=None,
        )
        async def process(city: str) -> str:
            calls["n"] += 1
            raise TypeError("non-retryable error")

        result = process.run(data=[{"city": "NYC"}])
        assert result.ok is False
        assert calls["n"] == 1  # no retries — failed immediately


class TestValidationErrors:
    def test_empty_data_raises(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return "ok"

        with pytest.raises(ValidationError):
            process.run(data=[])

    def test_missing_required_arg_raises(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str, model: str) -> str:
            return "ok"

        with pytest.raises(ValidationError):
            process.run(data=[{"city": "NYC"}])  # missing model

    def test_extra_key_raises(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return "ok"

        with pytest.raises(ValidationError):
            process.run(data=[{"city": "NYC", "extra": "bad"}])


class TestDuplicateInputs:
    def test_duplicate_inputs_tracked_independently(self):
        """Same input at different indices should be processed independently."""
        @parawave(max_concurrency=5, storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        # Same city twice
        result = process.run(data=[{"city": "NYC"}, {"city": "NYC"}])
        assert result.ok is True
        assert len(result) == 2
        assert result[0].output == "processed NYC"
        assert result[1].output == "processed NYC"
        assert result[0].index == 0
        assert result[1].index == 1


class TestRateLimiting:
    def test_rate_limit_works(self):
        import time

        @parawave(
            max_concurrency=10,
            rate_limit=5,
            rate_period=1,
            storage="in_memory",
            progress=None,
        )
        async def process(city: str) -> str:
            return f"processed {city}"

        start = time.monotonic()
        result = process.run(data=make_city_data(10))
        elapsed = time.monotonic() - start

        assert result.ok is True
        # 10 items at 5/s should take ~1s minimum
        assert elapsed >= 0.8
