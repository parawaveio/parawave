"""Tests for Engine — orchestration core."""

import asyncio

import pytest

from parawave.engine import Engine, EngineConfig
from parawave.retry import RetryPolicy
from parawave.storage.memory import InMemoryStorage


@pytest.fixture
def storage():
    return InMemoryStorage()


def make_config(**overrides) -> EngineConfig:
    defaults = dict(
        max_concurrency=5,
        rate_limit=None,
        rate_period=1,
        retry_policy=None,
        task_timeout=60,
        stop_on_consecutive_failures=None,
        progress=None,
        on_start=[],
        on_retry=[],
        on_item_complete=[],
        on_item_error=[],
        on_complete=[],
        warmup=False,
    )
    defaults.update(overrides)
    return EngineConfig(**defaults)


class TestBasicExecution:
    async def test_all_items_succeed(self, storage):
        async def process(city: str) -> str:
            return f"processed {city}"

        items = [{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]
        config = make_config()

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is True
        assert len(result) == 3
        assert result[0].output == "processed NYC"
        assert result[1].output == "processed LA"
        assert result[2].output == "processed Tokyo"

    async def test_mixed_success_and_failure(self, storage):
        async def process(city: str) -> str:
            if city == "LA":
                raise ValueError("LA is broken")
            return f"processed {city}"

        items = [{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]
        config = make_config()

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is False
        assert result[0].ok is True
        assert result[1].ok is False
        assert "LA is broken" in result[1].error
        assert result[2].ok is True

    async def test_all_items_fail(self, storage):
        async def process(city: str) -> str:
            raise ValueError("broken")

        items = [{"city": "NYC"}, {"city": "LA"}]
        config = make_config()

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is False
        assert all(item.status == "failed" for item in result)


class TestConcurrency:
    async def test_respects_max_concurrency(self, storage):
        max_concurrent = {"current": 0, "peak": 0}

        async def process(city: str) -> str:
            max_concurrent["current"] += 1
            max_concurrent["peak"] = max(max_concurrent["peak"], max_concurrent["current"])
            await asyncio.sleep(0.05)
            max_concurrent["current"] -= 1
            return f"processed {city}"

        items = [{"city": f"city_{i}"} for i in range(20)]
        config = make_config(max_concurrency=3)

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is True
        assert max_concurrent["peak"] <= 3


class TestRetry:
    async def test_retry_succeeds(self, storage):
        attempts = {"n": 0}

        async def process(city: str) -> str:
            attempts["n"] += 1
            if attempts["n"] <= 1:
                raise ValueError("transient")
            return f"processed {city}"

        items = [{"city": "NYC"}]
        policy = RetryPolicy(max_retries=2, backoff="fixed", base_delay=0.01)
        config = make_config(retry_policy=policy)

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is True


class TestStopOnConsecutiveFailures:
    async def test_stops_after_n_consecutive(self, storage):
        call_count = {"n": 0}

        async def process(city: str) -> str:
            call_count["n"] += 1
            if call_count["n"] > 3:
                raise ValueError("failing now")
            return f"processed {city}"

        items = [{"city": f"city_{i}"} for i in range(20)]
        config = make_config(max_concurrency=1, stop_on_consecutive_failures=3)

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is False
        assert len(result.pending) > 0
        assert result.num_failed >= 3


class TestRateLimit:
    async def test_rate_limit_throttles(self, storage):
        """With rate_limit=2 per second, 4 items should take ~1s."""
        import time

        async def process(city: str) -> str:
            return f"processed {city}"

        items = [{"city": f"city_{i}"} for i in range(4)]
        config = make_config(max_concurrency=10, rate_limit=2, rate_period=1)

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )

        start = time.monotonic()
        result = await engine.run()
        elapsed = time.monotonic() - start

        assert result.ok is True
        # 4 items at 2/second = at least ~1 second (with tolerance)
        assert elapsed >= 0.8


class TestHooks:
    async def test_on_start_fires(self, storage):
        calls = []

        def on_start(run_id, total):
            calls.append(("start", run_id, total))

        async def process(city: str) -> str:
            return "ok"

        items = [{"city": "NYC"}]
        config = make_config(on_start=[on_start])

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        await engine.run()

        assert len(calls) == 1
        assert calls[0][0] == "start"

    async def test_on_item_complete_fires(self, storage):
        calls = []

        def on_item_complete(item):
            calls.append(item.index)

        async def process(city: str) -> str:
            return "ok"

        items = [{"city": "NYC"}, {"city": "LA"}]
        config = make_config(on_item_complete=[on_item_complete])

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        await engine.run()

        assert sorted(calls) == [0, 1]

    async def test_on_item_error_fires(self, storage):
        error_calls = []

        def on_item_error(item):
            error_calls.append(item.index)

        async def process(city: str) -> str:
            raise ValueError("fail")

        items = [{"city": "NYC"}, {"city": "LA"}]
        config = make_config(on_item_error=[on_item_error])

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        await engine.run()

        assert sorted(error_calls) == [0, 1]

    async def test_on_complete_receives_result(self, storage):
        results = []

        def on_complete(result):
            results.append(result)

        async def process(city: str) -> str:
            return "ok"

        items = [{"city": "NYC"}]
        config = make_config(on_complete=[on_complete])

        engine = Engine(
            func=process, is_async=True, items=items, config=config, storage=storage
        )
        await engine.run()

        assert len(results) == 1
        assert results[0].ok is True


class TestSyncFunction:
    async def test_sync_function_works(self, storage):
        def process(city: str) -> str:
            return f"processed {city}"

        items = [{"city": "NYC"}, {"city": "LA"}]
        config = make_config()

        engine = Engine(
            func=process, is_async=False, items=items, config=config, storage=storage
        )
        result = await engine.run()

        assert result.ok is True
        assert result[0].output == "processed NYC"


class TestEngineRunTimeout:
    async def test_run_timeout_stops_execution(self):
        async def slow_fn(x):
            await asyncio.sleep(10)
            return x

        items = [{"x": i} for i in range(5)]
        config = EngineConfig(max_concurrency=1, task_timeout=30, run_timeout=0.2)
        storage = InMemoryStorage()
        await storage.create_run("run-t", {}, "hash", items)

        engine = Engine(
            func=slow_fn, is_async=True, items=items,
            config=config, storage=storage, run_id="run-t",
        )
        result = await engine.run()
        assert result.num_pending > 0
        assert result.elapsed < 1.0


class TestEngineOnRetryHooks:
    async def test_on_retry_hooks_fire_through_engine(self):
        call_count = 0
        hook_calls = []

        async def fail_then_succeed(x):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return x

        def capture(item):
            hook_calls.append(item)

        items = [{"x": 1}]
        config = EngineConfig(
            max_concurrency=1,
            retry_policy=RetryPolicy(max_retries=1, backoff="fixed", base_delay=0.01),
            on_retry=[capture],
        )
        storage = InMemoryStorage()
        await storage.create_run("run-h", {}, "hash", items)

        engine = Engine(
            func=fail_then_succeed, is_async=True, items=items,
            config=config, storage=storage, run_id="run-h",
        )
        result = await engine.run()
        assert result.ok
        assert len(hook_calls) == 1


class TestEngineElapsedPersist:
    async def test_elapsed_persisted_to_storage(self):
        async def slow_fn(x):
            await asyncio.sleep(0.05)
            return x

        items = [{"x": 1}]
        config = EngineConfig(max_concurrency=1)
        storage = InMemoryStorage()
        await storage.create_run("run-e", {}, "hash", items)

        engine = Engine(
            func=slow_fn, is_async=True, items=items,
            config=config, storage=storage, run_id="run-e",
        )
        result = await engine.run()
        assert result[0].elapsed >= 0.04

        stored_items = await storage.get_all_items("run-e")
        assert stored_items[0].elapsed >= 0.04


class TestWarmupMode:
    async def test_warmup_success_runs_all_items(self, storage):
        """Warmup succeeds on first item, then all items complete."""
        results = []

        async def process(x: int) -> int:
            results.append(x)
            return x * 2

        items = [{"x": 1}, {"x": 2}, {"x": 3}, {"x": 4}, {"x": 5}]
        config = make_config(max_concurrency=3, warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert result.num_completed == 5
        assert result[0].output == 2
        assert set(results) == {1, 2, 3, 4, 5}

    async def test_warmup_failure_stops_run(self, storage):
        """Warmup fails on first item, remaining items are pending."""
        async def process(x: int) -> int:
            raise ValueError("always fails")

        items = [{"x": 1}, {"x": 2}, {"x": 3}]
        config = make_config(max_concurrency=3, warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is False
        assert result[0].status == "failed"
        assert result[1].status == "pending"
        assert result[2].status == "pending"

    async def test_warmup_false_runs_all_concurrently(self, storage):
        """warmup=False should behave exactly like before."""
        async def process(x: int) -> int:
            return x * 2

        items = [{"x": 1}, {"x": 2}, {"x": 3}]
        config = make_config(max_concurrency=3, warmup=False)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert result.num_completed == 3

    async def test_warmup_single_item(self, storage):
        """Warmup with one item should work — it's the entire run."""
        async def process(x: int) -> int:
            return x * 2

        items = [{"x": 1}]
        config = make_config(warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert result.num_completed == 1
        assert result[0].output == 2

    async def test_warmup_respects_retry(self, storage):
        """Warmup item should be retried before declaring failure."""
        attempts = {"n": 0}

        async def process(x: int) -> int:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("transient")
            return x * 2

        items = [{"x": 1}, {"x": 2}]
        policy = RetryPolicy(max_retries=2, backoff="fixed", base_delay=0.01)
        config = make_config(max_concurrency=2, retry_policy=policy, warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert result.num_completed == 2
        assert result[0].attempts == 2

    async def test_warmup_fires_hooks(self, storage):
        """Hooks should fire during warmup."""
        completed_items = []

        async def process(x: int) -> int:
            return x * 2

        def on_item_done(item):
            completed_items.append(item.index)

        items = [{"x": 1}, {"x": 2}]
        config = make_config(on_item_complete=[on_item_done], warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert 0 in completed_items

    async def test_warmup_respects_task_timeout(self, storage):
        """Warmup item should be killed by task_timeout."""
        async def slow(x: int) -> int:
            await asyncio.sleep(10)
            return x

        items = [{"x": 1}, {"x": 2}]
        config = make_config(task_timeout=0.1, warmup=True)
        engine = Engine(
            func=slow, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result[0].status == "failed"
        assert result[1].status == "pending"

    async def test_warmup_item0_included_in_result(self, storage):
        """Item 0 result should be in the final Result, not discarded."""
        order = []

        async def process(x: int) -> int:
            order.append(x)
            return x * 2

        items = [{"x": 10}, {"x": 20}, {"x": 30}]
        config = make_config(max_concurrency=2, warmup=True)
        engine = Engine(
            func=process, is_async=True, items=items,
            config=config, storage=storage,
        )
        result = await engine.run()

        assert result.ok is True
        assert result[0].output == 20
        assert result[1].output == 40
        assert result[2].output == 60
        assert order[0] == 10


class TestEngineStatusAndElapsed:
    async def test_engine_sets_status_completed(self):
        storage = InMemoryStorage()
        items = [{"x": 1}]
        config = EngineConfig(max_concurrency=1, progress=None)
        engine = Engine(
            func=lambda x: x, is_async=False, items=items,
            config=config, storage=storage,
        )
        await storage.create_run(engine.run_id, {}, "hash", items)
        await engine.run()
        record = await storage.get_run(engine.run_id)
        assert record.status == "completed"

    async def test_engine_writes_elapsed(self):
        storage = InMemoryStorage()
        items = [{"x": 1}]
        config = EngineConfig(max_concurrency=1, progress=None)
        engine = Engine(
            func=lambda x: x, is_async=False, items=items,
            config=config, storage=storage,
        )
        await storage.create_run(engine.run_id, {}, "hash", items)
        result = await engine.run()
        elapsed = await storage.get_run_elapsed(engine.run_id)
        assert elapsed > 0
        assert result.elapsed == elapsed

    async def test_engine_passes_tags_to_result(self):
        storage = InMemoryStorage()
        items = [{"x": 1}]
        config = EngineConfig(max_concurrency=1, progress=None)
        engine = Engine(
            func=lambda x: x, is_async=False, items=items,
            config=config, storage=storage,
            tags={"stage": "test"},
        )
        await storage.create_run(engine.run_id, {}, "hash", items,
                                 tags={"stage": "test"})
        result = await engine.run()
        assert result.tags == {"stage": "test"}
