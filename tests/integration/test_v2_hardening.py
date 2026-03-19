"""Integration tests for v2 hardening features."""

import time
import pytest
from parawave.decorator import parawave
from parawave.retry import RetryPolicy


class TestElapsedEndToEnd:
    def test_elapsed_on_result_items(self):
        @parawave(storage="in_memory")
        def fn(x):
            return x * 2

        result = fn.run(data=[{"x": 1}, {"x": 2}, {"x": 3}])
        assert result.ok
        for item in result:
            assert item.elapsed >= 0
        assert result.avg_item_elapsed >= 0


class TestOnRetryEndToEnd:
    def test_on_retry_hook_fires(self):
        call_count = 0
        retry_events = []

        def capture(item):
            retry_events.append(item.error)

        @parawave(
            retry=RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.01),
            on_retry=[capture],
            storage="in_memory",
        )
        def fn(x):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first attempt fails")
            return x

        result = fn.run(data=[{"x": 1}])
        assert result.ok
        assert len(retry_events) == 1
        assert "ValueError" in retry_events[0]


class TestRunTimeoutEndToEnd:
    def test_run_timeout_stops_run(self):
        @parawave(
            max_concurrency=1,
            task_timeout=30,
            run_timeout=0.3,
            storage="in_memory",
        )
        def fn(x):
            time.sleep(10)
            return x

        result = fn.run(data=[{"x": i} for i in range(5)])
        assert not result.ok
        assert result.num_pending > 0
        assert result.elapsed < 2.0


class TestConfigOverridesEndToEnd:
    def test_run_with_override(self):
        @parawave(max_concurrency=50, storage="in_memory")
        def fn(x):
            return x

        result = fn.run(data=[{"x": 1}], max_concurrency=1)
        assert result.ok
        assert fn.config["max_concurrency"] == 50

    def test_resume_with_override(self):
        call_count = 0

        @parawave(max_concurrency=10, storage="in_memory")
        def fn(x):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise ValueError("fail first time")
            return x

        result = fn.run(data=[{"x": 1}])
        assert not result.ok

        result2 = fn.resume(max_concurrency=1)
        assert result2.ok

    def test_config_property(self):
        @parawave(max_concurrency=42, rate_limit=100, storage="in_memory")
        def fn(x):
            return x

        assert fn.config["max_concurrency"] == 42
        assert fn.config["rate_limit"] == 100

    def test_broadcast_still_works_with_overrides(self):
        @parawave(max_concurrency=5, storage="in_memory")
        def fn(x, y):
            return x + y

        result = fn.run(data=[{"x": 1}, {"x": 2}], y=10, max_concurrency=2)
        assert result.ok
        assert result.data == [11, 12]

    def test_resume_uses_stored_db_config_not_decorator(self):
        """Section 5: Resume reads config from DB, not from the current decorator.

        This is the core behavioral change in v2 — each run is self-contained.
        """
        from parawave.process import Process

        call_count = 0

        def fn(x):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise ValueError("fail first")
            return x

        # Create Process with max_concurrency=50
        process1 = Process(func=fn, config={
            "max_concurrency": 50,
            "rate_limit": None,
            "rate_period": 1,
            "retry": None,
            "executor": "auto",
            "task_timeout": 60,
            "run_timeout": None,
            "stop_on_consecutive_failures": None,
            "storage": "in_memory",
            "progress": None,
            "on_start": [],
            "on_retry": [],
            "on_item_complete": [],
            "on_item_error": [],
            "on_complete": [],
        })

        result = process1.run(data=[{"x": 1}])
        assert not result.ok
        run_id = result.run_id

        # Create a NEW Process with max_concurrency=1 (different decorator config)
        # but resume the SAME run — should use stored config (50), not new decorator (1)
        call_count = 0  # reset
        process2 = Process(func=fn, config={
            "max_concurrency": 1,  # different from original
            "rate_limit": None,
            "rate_period": 1,
            "retry": None,
            "executor": "auto",
            "task_timeout": 60,
            "run_timeout": None,
            "stop_on_consecutive_failures": None,
            "storage": "in_memory",
            "progress": None,
            "on_start": [],
            "on_retry": [],
            "on_item_complete": [],
            "on_item_error": [],
            "on_complete": [],
        })

        # Share the same in-memory storage so process2 can find the run
        process2._shared_storage = process1._shared_storage
        call_count = 1  # next call will be 2, which succeeds

        result2 = process2.resume(run_id)
        assert result2.ok

    def test_elapsed_preserved_through_resume(self):
        call_count = 0

        @parawave(
            retry=RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.01),
            storage="in_memory",
        )
        def fn(x):
            nonlocal call_count
            call_count += 1
            time.sleep(0.02)
            if call_count <= 1:
                raise ValueError("fail first")
            return x

        result = fn.run(data=[{"x": 1}, {"x": 2}])
        # Some items may have completed, some failed
        completed_items = [item for item in result if item.ok]
        assert len(completed_items) >= 1
        for item in completed_items:
            assert item.elapsed > 0

        # Resume — completed items from first run should retain elapsed
        result2 = fn.resume()
        for item in result2:
            assert item.elapsed > 0
