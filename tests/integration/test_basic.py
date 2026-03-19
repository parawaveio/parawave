"""Integration tests — basic end-to-end scenarios."""

import parawave
from parawave import RetryPolicy, SharedState


class TestHelloWorld:
    def test_minimal_example(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        cities = ["NYC", "LA", "Tokyo"]
        result = process.run(data=[{"city": c} for c in cities])

        assert result.ok is True
        assert result.summary.startswith("3/3 completed")
        assert len(result) == 3
        for i, city in enumerate(cities):
            assert result[i].output == f"processed {city}"

    def test_data_property(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        result = process.run(data=[{"city": "NYC"}, {"city": "LA"}])
        assert result.data == ["processed NYC", "processed LA"]


class TestSyncFunction:
    def test_sync_function_works(self):
        @parawave(storage="in_memory", progress=None)
        def process(city: str) -> str:
            return f"processed {city}"

        result = process.run(data=[{"city": "NYC"}])
        assert result.ok is True
        assert result[0].output == "processed NYC"


class TestBroadcastKwargs:
    def test_broadcast_merge(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str, model: str) -> dict:
            return {"city": city, "model": model}

        result = process.run(
            data=[{"city": "NYC"}, {"city": "LA"}],
            model="gpt-4",
        )
        assert result.ok is True
        assert result[0].output["model"] == "gpt-4"
        assert result[1].output["model"] == "gpt-4"

    def test_item_overrides_broadcast(self):
        @parawave(storage="in_memory", progress=None)
        async def process(city: str, model: str) -> dict:
            return {"city": city, "model": model}

        result = process.run(
            data=[{"city": "NYC", "model": "gpt-3.5"}, {"city": "LA"}],
            model="gpt-4",
        )
        assert result[0].output["model"] == "gpt-3.5"
        assert result[1].output["model"] == "gpt-4"


class TestSharedState:
    def test_shared_state_across_items(self):
        state = SharedState({"count": 0, "cities": []})

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def process(city: str) -> str:
            state.increment("count")
            state.append("cities", city)
            return f"processed {city}"

        result = process.run(data=[{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}])
        assert result.ok is True
        assert state.get("count") == 3
        assert len(state.get("cities")) == 3


class TestMockLLMCall:
    def test_mock_llm_integration(self):
        """Demonstrates the mock LLM call pattern for testing."""
        from tests.helpers import mock_llm_call, make_llm_data

        @parawave(max_concurrency=5, storage="in_memory", progress=None)
        async def process(prompt: str, model: str = "mock-gpt") -> dict:
            return await mock_llm_call(prompt=prompt, model=model)

        result = process.run(data=make_llm_data(10))
        assert result.ok is True
        assert all(item.output["model"] == "mock-gpt" for item in result)


class TestHooks:
    def test_all_hooks_fire(self):
        events = []

        def on_start(run_id, total):
            events.append(("start", total))

        def on_item_complete(item):
            events.append(("item_complete", item.index))

        def on_complete(result):
            events.append(("complete", result.ok))

        @parawave(
            max_concurrency=1,
            storage="in_memory",
            progress=None,
            on_start=[on_start],
            on_item_complete=[on_item_complete],
            on_complete=[on_complete],
        )
        async def process(city: str) -> str:
            return "ok"

        result = process.run(data=[{"city": "NYC"}, {"city": "LA"}])
        assert result.ok is True

        assert ("start", 2) in events
        assert ("complete", True) in events
        assert len([e for e in events if e[0] == "item_complete"]) == 2


class TestLargerBatch:
    def test_100_items(self):
        @parawave(max_concurrency=20, storage="in_memory", progress=None)
        async def process(city: str) -> str:
            return f"processed {city}"

        from tests.helpers import make_city_data
        result = process.run(data=make_city_data(100))

        assert result.ok is True
        assert len(result) == 100
        assert result.summary.startswith("100/100 completed")
