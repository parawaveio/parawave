"""Tests for SQLite metadata store."""

import pytest
from datetime import datetime

from parawave.storage.sqlite.sqlite import SqliteStore


@pytest.fixture
async def store(tmp_path):
    s = SqliteStore(tmp_path / "test.db")
    await s.initialize()
    yield s
    await s.close()


class TestRunOperations:
    async def test_create_and_get_run(self, store):
        await store.create_run("run-1", {"max_concurrency": 10}, "hash123", 3)
        record = await store.get_run("run-1")
        assert record.run_id == "run-1"
        assert record.func_hash == "hash123"
        assert record.total_items == 3

    async def test_run_exists(self, store):
        assert await store.run_exists("run-1") is False
        await store.create_run("run-1", {}, "hash", 1)
        assert await store.run_exists("run-1") is True


class TestItemOperations:
    async def test_create_items_and_get_all(self, store):
        await store.create_run("run-1", {}, "hash", 3)
        hashes = ["h0", "h1", "h2"]
        await store.create_items("run-1", 3, hashes)

        items = await store.get_all_items("run-1")
        assert len(items) == 3
        assert all(item.status == "pending" for item in items)
        assert [item.index for item in items] == [0, 1, 2]

    async def test_update_status(self, store):
        await store.create_run("run-1", {}, "hash", 2)
        await store.create_items("run-1", 2, ["h0", "h1"])

        await store.update_item_status("run-1", 0, "completed", None)
        await store.update_item_status("run-1", 1, "failed", "bad input")

        items = await store.get_all_items("run-1")
        assert items[0].status == "completed"
        assert items[0].error is None
        assert items[1].status == "failed"
        assert items[1].error == "bad input"

    async def test_get_items_by_status(self, store):
        await store.create_run("run-1", {}, "hash", 3)
        await store.create_items("run-1", 3, ["h0", "h1", "h2"])
        await store.update_item_status("run-1", 0, "completed", None)

        pending = await store.get_items_by_status("run-1", "pending")
        assert len(pending) == 2

        completed = await store.get_items_by_status("run-1", "completed")
        assert len(completed) == 1

    async def test_get_input_hash(self, store):
        await store.create_run("run-1", {}, "hash", 2)
        await store.create_items("run-1", 2, ["hash_a", "hash_b"])
        assert await store.get_item_input_hash("run-1", 0) == "hash_a"
        assert await store.get_item_input_hash("run-1", 1) == "hash_b"


class TestSqliteElapsed:
    async def test_update_item_status_with_elapsed(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        await store.create_items("run-1", 1, ["inputhash"])
        await store.update_item_status("run-1", 0, "completed", None, attempts=1, elapsed=3.7)
        items = await store.get_all_items("run-1")
        assert items[0].elapsed == pytest.approx(3.7)

    async def test_elapsed_defaults_to_zero_in_schema(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        await store.create_items("run-1", 1, ["inputhash"])
        items = await store.get_all_items("run-1")
        assert items[0].elapsed == 0.0


class TestSqliteUpdateRunConfig:
    async def test_update_run_config(self, store):
        await store.create_run("run-1", {"max_concurrency": 10}, "hash", 1)
        await store.update_run_config("run-1", {"max_concurrency": 5})
        run = await store.get_run("run-1")
        assert run.config == {"max_concurrency": 5}


class TestNewRunColumns:
    async def test_create_run_with_tags(self, store):
        await store.create_run(
            "run-1", {"max_concurrency": 10}, "hash123", 3,
            tags={"stage": "generate"}, created_at="2026-03-16T21:00:00+00:00",
        )
        record = await store.get_run("run-1")
        assert record.tags == {"stage": "generate"}
        assert record.created_at == "2026-03-16T21:00:00+00:00"
        assert record.status == "running"
        assert record.elapsed == 0.0

    async def test_create_run_without_tags(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        record = await store.get_run("run-1")
        assert record.tags is None
        assert record.status == "running"

    async def test_update_run_status(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        await store.update_run_status("run-1", "completed")
        record = await store.get_run("run-1")
        assert record.status == "completed"

    async def test_update_run_elapsed(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        await store.update_run_elapsed("run-1", 70.5)
        assert await store.get_run_elapsed("run-1") == 70.5

    async def test_elapsed_accumulation(self, store):
        await store.create_run("run-1", {}, "hash", 1)
        await store.update_run_elapsed("run-1", 70.0)
        stored = await store.get_run_elapsed("run-1")
        await store.update_run_elapsed("run-1", stored + 65.0)
        assert await store.get_run_elapsed("run-1") == 135.0

    async def test_update_tags(self, store):
        await store.create_run("run-1", {}, "hash", 1,
                               tags={"stage": "generate"})
        await store.update_tags("run-1", {"stage": "generate", "quality": "approved"})
        record = await store.get_run("run-1")
        assert record.tags == {"stage": "generate", "quality": "approved"}

    async def test_delete_run(self, store):
        await store.create_run("run-1", {}, "hash", 2)
        await store.create_items("run-1", 2, ["h0", "h1"])
        await store.delete_run("run-1")
        assert await store.run_exists("run-1") is False

    async def test_get_run_info(self, store):
        await store.create_run("run-1", {}, "hash", 3,
                               tags={"stage": "gen"},
                               created_at="2026-03-16T21:00:00+00:00")
        await store.create_items("run-1", 3, ["h0", "h1", "h2"])
        await store.update_item_status("run-1", 0, "completed", None, attempts=1)
        await store.update_item_status("run-1", 1, "completed", None, attempts=2)
        await store.update_item_status("run-1", 2, "failed", "err", attempts=3)

        info = await store.get_run_info("run-1")
        assert info.run_id == "run-1"
        assert info.num_completed == 2
        assert info.num_failed == 1
        assert info.num_pending == 0
        assert info.num_retried == 2
        assert info.num_attempts == 6
        assert info.tags == {"stage": "gen"}
        assert isinstance(info.created_at, datetime)

    async def test_list_runs_all(self, store):
        await store.create_run("run-1", {}, "hash", 1,
                               created_at="2026-03-16T20:00:00+00:00")
        await store.create_items("run-1", 1, ["h0"])
        await store.create_run("run-2", {}, "hash", 1,
                               created_at="2026-03-16T21:00:00+00:00")
        await store.create_items("run-2", 1, ["h0"])

        runs = await store.list_runs()
        assert len(runs) == 2
        assert runs[0].run_id == "run-2"  # newest first

    async def test_list_runs_filter_by_tags(self, store):
        await store.create_run("run-1", {}, "hash", 1,
                               tags={"stage": "generate"},
                               created_at="2026-03-16T20:00:00+00:00")
        await store.create_items("run-1", 1, ["h0"])
        await store.create_run("run-2", {}, "hash", 1,
                               tags={"stage": "judge"},
                               created_at="2026-03-16T21:00:00+00:00")
        await store.create_items("run-2", 1, ["h0"])

        runs = await store.list_runs(tags={"stage": "generate"})
        assert len(runs) == 1
        assert runs[0].run_id == "run-1"

    async def test_list_runs_filter_by_status(self, store):
        await store.create_run("run-1", {}, "hash", 1,
                               created_at="2026-03-16T20:00:00+00:00")
        await store.create_items("run-1", 1, ["h0"])
        await store.update_run_status("run-1", "completed")
        await store.create_run("run-2", {}, "hash", 1,
                               created_at="2026-03-16T21:00:00+00:00")
        await store.create_items("run-2", 1, ["h0"])

        runs = await store.list_runs(status="running")
        assert len(runs) == 1
        assert runs[0].run_id == "run-2"

    async def test_list_runs_exact_tag_match(self, store):
        """Tags filter should use exact matching, not substring."""
        await store.create_run("run-1", {}, "hash", 1,
                               tags={"stage": "judge-gpt"},
                               created_at="2026-03-16T20:00:00+00:00")
        await store.create_items("run-1", 1, ["h0"])

        # "judge" should NOT match "judge-gpt"
        runs = await store.list_runs(tags={"stage": "judge"})
        assert len(runs) == 0

        # exact match works
        runs = await store.list_runs(tags={"stage": "judge-gpt"})
        assert len(runs) == 1


class TestTagValidation:
    async def test_list_runs_rejects_unsafe_tag_keys(self, store):
        with pytest.raises(ValueError, match="Invalid tag key"):
            await store.list_runs(tags={"'; DROP TABLE": "x"})

    async def test_update_tags_empty_dict(self, store):
        await store.create_run("run-1", {}, "hash", 1, tags={"a": "1"})
        await store.update_tags("run-1", {})
        record = await store.get_run("run-1")
        assert record.tags == {}
