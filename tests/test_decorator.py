"""Tests for the @parawave() decorator."""

import pytest

from parawave.decorator import parawave
from parawave.process import Process
from parawave.errors import ValidationError


class TestDecorator:
    def test_creates_process(self):
        @parawave()
        async def process(city: str) -> str:
            return f"processed {city}"

        assert isinstance(process, Process)

    def test_preserves_function_name(self):
        @parawave()
        async def my_function(city: str) -> str:
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_run_works(self):
        @parawave(max_concurrency=5, storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        result = process.run(data=[{"city": "NYC"}, {"city": "LA"}])
        assert result.ok is True
        assert result[0].output == "processed NYC"

    def test_sync_function(self):
        @parawave(storage="in_memory", progress=None)
        def process(city: str) -> str:
            return f"processed {city}"

        result = process.run(data=[{"city": "NYC"}])
        assert result.ok is True

    def test_executor_async_with_sync_raises(self):
        with pytest.raises(ValidationError, match="executor"):
            @parawave(executor="async")
            def process(city: str) -> str:
                return "ok"

    def test_executor_thread_with_async_raises(self):
        with pytest.raises(ValidationError, match="executor"):
            @parawave(executor="thread")
            async def process(city: str) -> str:
                return "ok"

    def test_minimal_config(self):
        @parawave()
        async def process(city: str) -> str:
            return "ok"

        assert isinstance(process, Process)

    def test_full_config(self):
        from parawave.retry import RetryPolicy

        @parawave(
            max_concurrency=20,
            rate_limit=100,
            rate_period=60,
            retry=RetryPolicy(max_retries=3),
            executor="auto",
            task_timeout=120,
            stop_on_consecutive_failures=5,
            storage="in_memory",
            progress=None,
            on_start=[],
            on_item_complete=[],
            on_item_error=[],
            on_complete=[],
        )
        async def process(city: str) -> str:
            return "ok"

        assert isinstance(process, Process)


class TestDecoratorOnRetry:
    def test_on_retry_in_config(self):
        def my_hook(item): pass

        @parawave(on_retry=[my_hook])
        def fn(x): return x

        assert fn._config["on_retry"] == [my_hook]

    def test_on_retry_defaults_to_empty(self):
        @parawave()
        def fn(x): return x

        assert fn._config["on_retry"] == []


class TestDecoratorRunTimeout:
    def test_run_timeout_in_config(self):
        @parawave(run_timeout=300)
        def fn(x): return x

        assert fn._config["run_timeout"] == 300

    def test_run_timeout_defaults_to_none(self):
        @parawave()
        def fn(x): return x

        assert fn._config["run_timeout"] is None

    def test_run_timeout_zero_raises(self):
        with pytest.raises(ValidationError):
            @parawave(run_timeout=0)
            def fn(x): return x

    def test_run_timeout_negative_raises(self):
        with pytest.raises(ValidationError):
            @parawave(run_timeout=-1)
            def fn(x): return x
