"""Tests for InMemoryStorage."""

import pytest

from parawave.storage.memory import InMemoryStorage
from parawave.storage.models import RunInfo
from parawave.result import Result
from parawave.errors import RunNotFoundError


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


class TestRunLifecycle:
    async def test_create_and_get_run(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        record = await storage.get_run("run-1")
        assert record.run_id == "run-1"
        assert record.func_hash == "hash123"
        assert record.total_items == 3

    async def test_run_exists(self, storage, sample_items, sample_config):
        assert await storage.run_exists("run-1") is False
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        assert await storage.run_exists("run-1") is True

    async def test_get_nonexistent_run_raises(self, storage):
        with pytest.raises(RunNotFoundError):
            await storage.get_run("nonexistent")


class TestItemStatus:
    async def test_initial_status_is_pending(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        items = await storage.get_all_items("run-1")
        assert len(items) == 3
        assert all(item.status == "pending" for item in items)

    async def test_update_item_status(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        await storage.update_item_status("run-1", 0, "completed", None)
        await storage.update_item_status("run-1", 1, "failed", "some error")

        items = await storage.get_all_items("run-1")
        assert items[0].status == "completed"
        assert items[1].status == "failed"
        assert items[1].error == "some error"
        assert items[2].status == "pending"

    async def test_get_items_by_status(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        await storage.update_item_status("run-1", 0, "completed", None)
        await storage.update_item_status("run-1", 1, "failed", "RuntimeError: test error")

        pending = await storage.get_items_by_status("run-1", "pending")
        assert len(pending) == 1
        assert pending[0].index == 2

        failed = await storage.get_items_by_status("run-1", "failed")
        assert len(failed) == 1
        assert failed[0].index == 1


class TestDataIO:
    async def test_save_and_load_output(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        await storage.save_item_output("run-1", 0, {"result": "processed NYC"})

        output = await storage.load_item_output("run-1", 0)
        assert output == {"result": "processed NYC"}

    async def test_load_item_input(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        input_data = await storage.load_item_input("run-1", 0)
        assert input_data == {"city": "NYC"}

    async def test_get_item_input_hash(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        hash_val = await storage.get_item_input_hash("run-1", 0)
        assert isinstance(hash_val, str)
        assert len(hash_val) > 0

    async def test_same_input_same_hash(self, storage, sample_config):
        items = [{"city": "NYC"}, {"city": "NYC"}]
        await storage.create_run("run-1", sample_config, "hash123", items)
        hash0 = await storage.get_item_input_hash("run-1", 0)
        hash1 = await storage.get_item_input_hash("run-1", 1)
        assert hash0 == hash1

    async def test_different_input_different_hash(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        hash0 = await storage.get_item_input_hash("run-1", 0)
        hash1 = await storage.get_item_input_hash("run-1", 1)
        assert hash0 != hash1


class TestClose:
    async def test_close_is_noop(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items)
        await storage.close()  # should not raise


class TestInMemoryElapsed:
    @pytest.fixture
    def storage(self):
        return InMemoryStorage()

    async def test_update_item_status_with_elapsed(self, storage):
        await storage.create_run("run-1", {}, "hash", [{"city": "NYC"}])
        await storage.update_item_status("run-1", 0, "completed", None, attempts=1, elapsed=2.5)
        items = await storage.get_all_items("run-1")
        assert items[0].elapsed == 2.5

    async def test_elapsed_defaults_to_zero(self, storage):
        await storage.create_run("run-1", {}, "hash", [{"city": "NYC"}])
        items = await storage.get_all_items("run-1")
        assert items[0].elapsed == 0.0


class TestInMemoryUpdateRunConfig:
    @pytest.fixture
    def storage(self):
        return InMemoryStorage()

    async def test_update_run_config(self, storage):
        await storage.create_run("run-1", {"max_concurrency": 10}, "hash", [{"city": "NYC"}])
        await storage.update_run_config("run-1", {"max_concurrency": 5})
        run = await storage.get_run("run-1")
        assert run.config == {"max_concurrency": 5}

    async def test_update_run_config_preserves_other_fields(self, storage):
        await storage.create_run("run-1", {"max_concurrency": 10}, "hash", [{"city": "NYC"}])
        await storage.update_run_config("run-1", {"max_concurrency": 5})
        run = await storage.get_run("run-1")
        assert run.func_hash == "hash"
        assert run.total_items == 1


class TestManagement:
    async def test_create_run_with_tags(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash123", sample_items,
                                 tags={"stage": "generate"})
        record = await storage.get_run("run-1")
        assert record.tags == {"stage": "generate"}
        assert record.status == "running"
        assert record.created_at != ""

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
        assert isinstance(info, RunInfo)
        assert info.num_completed == 1
        assert info.num_pending == 2

    async def test_list_runs(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items)
        await storage.create_run("run-2", sample_config, "hash", sample_items)
        runs = await storage.list_runs()
        assert len(runs) == 2

    async def test_list_runs_filter_by_tags(self, storage, sample_config):
        await storage.create_run("run-1", sample_config, "hash", [{"x": 1}],
                                 tags={"stage": "generate"})
        await storage.create_run("run-2", sample_config, "hash", [{"x": 1}],
                                 tags={"stage": "judge"})
        runs = await storage.list_runs(tags={"stage": "generate"})
        assert len(runs) == 1
        assert runs[0].run_id == "run-1"

    async def test_list_runs_filter_by_status(self, storage, sample_config):
        await storage.create_run("run-1", sample_config, "hash", [{"x": 1}])
        await storage.update_run_status("run-1", "completed")
        await storage.create_run("run-2", sample_config, "hash", [{"x": 1}])
        runs = await storage.list_runs(status="running")
        assert len(runs) == 1
        assert runs[0].run_id == "run-2"

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
        assert isinstance(result, Result)
        assert len(result) == 3
        assert result[0].ok
        assert result[0].output == {"result": "ok"}

    async def test_update_run_config_preserves_new_fields(self, storage, sample_items, sample_config):
        await storage.create_run("run-1", sample_config, "hash", sample_items,
                                 tags={"stage": "gen"})
        await storage.update_run_status("run-1", "completed")
        await storage.update_run_elapsed("run-1", 50.0)
        await storage.update_run_config("run-1", {"max_concurrency": 20})
        record = await storage.get_run("run-1")
        assert record.config == {"max_concurrency": 20}
        assert record.tags == {"stage": "gen"}
        assert record.status == "completed"
        assert record.elapsed == 50.0


class TestManagementErrors:
    async def test_update_tags_not_found(self, storage):
        with pytest.raises(RunNotFoundError):
            await storage.update_tags("nonexistent", {"a": "1"})

    async def test_update_run_status_not_found(self, storage):
        with pytest.raises(RunNotFoundError):
            await storage.update_run_status("nonexistent", "completed")

    async def test_delete_run_not_found(self, storage):
        with pytest.raises(RunNotFoundError):
            await storage.delete_run("nonexistent")

    async def test_create_run_rejects_unsafe_tag_keys(self, storage, sample_config):
        with pytest.raises(ValueError, match="Invalid tag key"):
            await storage.create_run("run-1", sample_config, "hash", [{"x": 1}],
                                     tags={"bad key!": "value"})
