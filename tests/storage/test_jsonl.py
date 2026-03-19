"""Tests for JSONL data store."""

import pytest

from parawave.storage.sqlite.jsonl import JsonlStore


@pytest.fixture
def store(tmp_path):
    return JsonlStore(tmp_path / "test_run")


class TestJsonlStore:
    async def test_write_and_read_inputs(self, store):
        items = [{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]
        await store.write_inputs(items)

        for i, item in enumerate(items):
            loaded = await store.read_input(i)
            assert loaded == item

    async def test_write_and_read_output(self, store):
        await store.write_output(0, {"result": "processed NYC"})
        output = await store.read_output(0)
        assert output == {"result": "processed NYC"}

    async def test_read_missing_output_returns_none(self, store):
        output = await store.read_output(99)
        assert output is None

    async def test_multiple_outputs(self, store):
        await store.write_output(0, "out_0")
        await store.write_output(1, "out_1")
        await store.write_output(2, "out_2")

        assert await store.read_output(0) == "out_0"
        assert await store.read_output(1) == "out_1"
        assert await store.read_output(2) == "out_2"

    async def test_non_serializable_output_raises(self, store):
        """Non-JSON-serializable outputs should raise, not silently convert."""

        class Custom:
            def __repr__(self):
                return "Custom()"

        with pytest.raises((TypeError, ValueError)):
            await store.write_output(0, Custom())

    async def test_overwrite_output_returns_latest(self, store):
        """On retry, new output appended — read_output returns the latest."""
        await store.write_output(0, "first_result")
        await store.write_output(0, "retry_result")
        output = await store.read_output(0)
        assert output == "retry_result"

    async def test_creates_directory(self, tmp_path):
        store = JsonlStore(tmp_path / "nested" / "deep" / "run")
        items = [{"city": "NYC"}]
        await store.write_inputs(items)
        loaded = await store.read_input(0)
        assert loaded == {"city": "NYC"}


class TestJsonlStoreStrictSerialization:
    async def test_write_inputs_rejects_non_serializable(self, store):
        """write_inputs() should raise on non-JSON-serializable data."""

        class Custom:
            pass

        items = [{"obj": Custom()}]
        with pytest.raises((TypeError, ValueError)):
            await store.write_inputs(items)

    async def test_write_inputs_accepts_valid_json(self, store):
        items = [{"city": "NYC", "count": 5, "tags": ["a"], "meta": None}]
        await store.write_inputs(items)
        loaded = await store.read_input(0)
        assert loaded == items[0]
