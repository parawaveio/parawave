"""Tests for incremental per-item storage writes."""

import asyncio

import pytest

import parawave
from parawave import RetryPolicy
from parawave.engine import Engine, EngineConfig
from parawave.storage.memory import InMemoryStorage
from parawave.result import ResultItem
from tests.helpers import make_failing_for, make_city_data


class TestIncrementalWrites:
    def test_items_persisted_as_they_complete(self):
        """Each item should be in storage immediately after completion."""
        persisted_indices = []

        class TrackingStorage(InMemoryStorage):
            async def update_item_status(self, run_id, index, status, error, attempts=1, elapsed=0.0):
                await super().update_item_status(run_id, index, status, error, attempts, elapsed)
                if status == "completed":
                    persisted_indices.append(index)

        storage = TrackingStorage()

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        # Monkey-patch to use our tracking storage
        process._shared_storage = storage

        result = process.run(data=make_city_data(5))
        assert result.ok is True
        # All 5 items should have been persisted incrementally
        assert len(persisted_indices) == 5

    def test_failed_items_persisted_immediately(self):
        """Failed items should also be persisted as they complete."""
        persisted_statuses = []

        class TrackingStorage(InMemoryStorage):
            async def update_item_status(self, run_id, index, status, error, attempts=1, elapsed=0.0):
                await super().update_item_status(run_id, index, status, error, attempts, elapsed)
                persisted_statuses.append((index, status))

        storage = TrackingStorage()
        fn = make_failing_for({"city_1", "city_3"})

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def process(city: str) -> dict:
            return await fn(city=city)

        process._shared_storage = storage

        result = process.run(data=make_city_data(5))
        assert result.ok is False
        # All 5 should be persisted (3 completed + 2 failed)
        assert len(persisted_statuses) == 5
        failed = [s for s in persisted_statuses if s[1] == "failed"]
        assert len(failed) == 2

    def test_resume_uses_index_map(self):
        """Resume should correctly map local engine indices to storage indices."""
        calls = {"n": 0}

        async def process(city: str) -> str:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise ValueError("transient")
            return f"processed {city}"

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def wrapped(city: str) -> str:
            return await process(city=city)

        result1 = wrapped.run(data=[{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}])
        assert not result1.ok

        result2 = wrapped.resume()
        assert result2.ok is True
        assert result2.summary.startswith("3/3 completed")


class TestEngineIndexMap:
    def test_persist_item_uses_index_map(self):
        """Engine._persist_item should use index_map when provided."""
        storage = InMemoryStorage()

        async def run_test():
            await storage.create_run("test-run", {}, "hash", [
                {"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}
            ])

            config = EngineConfig(max_concurrency=1)
            # Local index 0 -> storage index 2 (simulating resume of item at index 2)
            index_map = {0: 2}

            engine = Engine(
                func=lambda city: f"processed {city}",
                is_async=False,
                items=[{"city": "Tokyo"}],
                config=config,
                storage=storage,
                run_id="test-run",
                index_map=index_map,
            )

            item = ResultItem(index=0, input={"city": "Tokyo"}, output="processed Tokyo", status="completed", error=None)
            await engine._persist_item(item)

            # Verify it was written to storage index 2, not 0
            items = await storage.get_items_by_status("test-run", "completed")
            assert any(i.index == 2 for i in items)
            await storage.close()

        asyncio.run(run_test())
