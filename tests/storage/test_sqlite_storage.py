"""Tests for SqliteStorage — full lifecycle combining SQLite + JSONL."""

import pytest

from parawave.storage.sqlite import SqliteStorage
from parawave.errors import RunNotFoundError


@pytest.fixture
async def storage(tmp_path):
    s = SqliteStorage(tmp_path / ".parawave")
    yield s
    await s.close()


@pytest.fixture
def sample_items() -> list[dict]:
    return [{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]


@pytest.fixture
def sample_config() -> dict:
    return {"max_concurrency": 10}


class TestFullLifecycle:
    async def test_create_run_and_process_items(self, storage):
        items = [{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]
        await storage.create_run("run-1", {"max_concurrency": 10}, "hash123", items)

        # All items start as pending
        all_items = await storage.get_all_items("run-1")
        assert len(all_items) == 3
        assert all(item.status == "pending" for item in all_items)

        # Process item 0
        await storage.save_item_output("run-1", 0, "processed NYC")
        await storage.update_item_status("run-1", 0, "completed", None)

        # Fail item 1
        await storage.update_item_status("run-1", 1, "failed", "timeout")

        # Check statuses
        completed = await storage.get_items_by_status("run-1", "completed")
        assert len(completed) == 1
        failed = await storage.get_items_by_status("run-1", "failed")
        assert len(failed) == 1
        pending = await storage.get_items_by_status("run-1", "pending")
        assert len(pending) == 1

        # Read back data
        output = await storage.load_item_output("run-1", 0)
        assert output == "processed NYC"
        input_data = await storage.load_item_input("run-1", 0)
        assert input_data == {"city": "NYC"}


class TestResumeScenario:
    async def test_resume_reads_back_all_data(self, storage):
        items = [{"city": "NYC"}, {"city": "LA"}]
        await storage.create_run("run-1", {}, "hash123", items)

        # Complete first item
        await storage.save_item_output("run-1", 0, "result_0")
        await storage.update_item_status("run-1", 0, "completed", None)

        # Fail second item
        await storage.update_item_status("run-1", 1, "failed", "RuntimeError: test error")

        # Simulate resume: check what needs to be retried
        run = await storage.get_run("run-1")
        assert run.func_hash == "hash123"

        to_retry = await storage.get_items_by_status("run-1", "failed")
        assert len(to_retry) == 1
        assert to_retry[0].index == 1

        # Verify input hash for safety check
        hash_val = await storage.get_item_input_hash("run-1", 1)
        assert isinstance(hash_val, str)


class TestRunExists:
    async def test_run_exists(self, storage):
        assert await storage.run_exists("run-1") is False
        await storage.create_run("run-1", {}, "hash", [{"a": 1}])
        assert await storage.run_exists("run-1") is True

    async def test_get_nonexistent_run(self, storage):
        with pytest.raises(RunNotFoundError):
            await storage.get_run("nonexistent")


class TestSqliteStorageManagement:
    async def test_create_run_with_tags(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items,
                                 tags={"stage": "generate"})
        record = await storage.get_run("run-1")
        assert record.tags == {"stage": "generate"}

    async def test_update_run_status(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.update_run_status("run-1", "completed")
        record = await storage.get_run("run-1")
        assert record.status == "completed"

    async def test_update_and_get_elapsed(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.update_run_elapsed("run-1", 42.5)
        assert await storage.get_run_elapsed("run-1") == 42.5

    async def test_get_run_info(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.update_item_status("run-1", 0, "completed", None)
        info = await storage.get_run_info("run-1")
        assert info.num_completed == 1
        assert info.num_pending == 2

    async def test_list_runs(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.create_run("run-2", sample_config, "hash", sample_items)
        runs = await storage.list_runs()
        assert len(runs) == 2

    async def test_update_tags(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items,
                                 tags={"a": "1"})
        await storage.update_tags("run-1", {"a": "1", "b": "2"})
        record = await storage.get_run("run-1")
        assert record.tags == {"a": "1", "b": "2"}

    async def test_delete_run(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.delete_run("run-1")
        assert await storage.run_exists("run-1") is False

    async def test_load_result(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.update_item_status("run-1", 0, "completed", None)
        await storage.save_item_output("run-1", 0, {"result": "ok"})
        await storage.update_item_status("run-1", 1, "failed", "err")
        await storage.update_item_status("run-1", 2, "completed", None)
        await storage.save_item_output("run-1", 2, {"result": "ok2"})

        result = await storage.load_result("run-1")
        assert len(result) == 3
        assert result[0].ok
        assert result[0].output == {"result": "ok"}
        assert not result[1].ok
        assert result[2].ok
