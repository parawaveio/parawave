"""Tests for RunManager."""

import pytest
from parawave.errors import RunNotFoundError
from parawave.storage.manager import RunManager
from parawave.storage.memory import InMemoryStorage
from parawave.storage.models import RunInfo
from parawave.result import Result
from parawave._event_loop import run_in_event_loop


@pytest.fixture
def memory_storage():
    return InMemoryStorage()


@pytest.fixture
def manager(memory_storage):
    return RunManager(storage=memory_storage)


def _seed_run(storage, run_id="run-1", tags=None, complete=True):
    """Seed a run into storage synchronously."""
    async def _do():
        items = [{"x": 1}, {"x": 2}, {"x": 3}]
        await storage.create_run(run_id, {"max_concurrency": 10}, "hash", items, tags=tags)
        await storage.update_item_status(run_id, 0, "completed", None)
        await storage.save_item_output(run_id, 0, "out0")
        await storage.update_item_status(run_id, 1, "completed", None)
        await storage.save_item_output(run_id, 1, "out1")
        await storage.update_item_status(run_id, 2, "failed", "err")
        if complete:
            await storage.update_run_status(run_id, "completed")
            await storage.update_run_elapsed(run_id, 10.0)
    run_in_event_loop(_do())


class TestRunManagerListRuns:
    def test_list_empty(self, manager):
        assert manager.list_runs() == []

    def test_list_all(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1")
        _seed_run(memory_storage, "run-2")
        runs = manager.list_runs()
        assert len(runs) == 2

    def test_list_filter_by_tags(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1", tags={"stage": "gen"})
        _seed_run(memory_storage, "run-2", tags={"stage": "judge"})
        runs = manager.list_runs(tags={"stage": "gen"})
        assert len(runs) == 1
        assert runs[0].run_id == "run-1"

    def test_list_filter_by_status(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1", complete=True)
        _seed_run(memory_storage, "run-2", complete=False)
        runs = manager.list_runs(status="running")
        assert len(runs) == 1
        assert runs[0].run_id == "run-2"


class TestRunManagerGet:
    def test_get(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1", tags={"a": "1"})
        info = manager.get("run-1")
        assert isinstance(info, RunInfo)
        assert info.run_id == "run-1"
        assert info.num_completed == 2
        assert info.num_failed == 1
        assert info.tags == {"a": "1"}


class TestRunManagerLoad:
    def test_load(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1")
        result = manager.load("run-1")
        assert isinstance(result, Result)
        assert len(result) == 3
        assert result.data[0] == "out0"


class TestRunManagerUpdateTags:
    def test_update_tags(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1", tags={"a": "1"})
        manager.update_tags("run-1", {"a": "1", "b": "2"})
        info = manager.get("run-1")
        assert info.tags == {"a": "1", "b": "2"}


class TestRunManagerDelete:
    def test_delete(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1")
        manager.delete("run-1")
        assert manager.list_runs() == []


class TestRunManagerErrors:
    def test_get_nonexistent_raises(self, manager):
        with pytest.raises(RunNotFoundError):
            manager.get("nonexistent")

    def test_load_nonexistent_raises(self, manager):
        with pytest.raises(RunNotFoundError):
            manager.load("nonexistent")

    def test_delete_nonexistent_raises(self, manager):
        with pytest.raises(RunNotFoundError):
            manager.delete("nonexistent")

    def test_update_tags_nonexistent_raises(self, manager):
        with pytest.raises(RunNotFoundError):
            manager.update_tags("nonexistent", {"a": "1"})


class TestRunManagerRequiresStorage:
    def test_no_default_raises_type_error(self):
        """RunManager() with no args should raise TypeError."""
        from parawave.storage.manager import RunManager
        with pytest.raises(TypeError, match="RunManager requires a storage backend"):
            RunManager()

    def test_error_lists_available_backends(self):
        """Error message should list available storage backends."""
        from parawave.storage.manager import RunManager
        with pytest.raises(TypeError) as exc_info:
            RunManager()
        msg = str(exc_info.value)
        assert "sqlite" in msg
        assert "in_memory" in msg

    def test_explicit_storage_works(self, tmp_path):
        """RunManager with explicit storage should work."""
        from parawave.storage.manager import RunManager
        manager = RunManager("sqlite", path=str(tmp_path / ".parawave"))
        runs = manager.list_runs()
        assert runs == []


class TestRunManagerCombinedFilters:
    def test_list_filter_by_tags_and_status(self, manager, memory_storage):
        _seed_run(memory_storage, "run-1", tags={"stage": "gen"}, complete=True)
        _seed_run(memory_storage, "run-2", tags={"stage": "gen"}, complete=False)
        _seed_run(memory_storage, "run-3", tags={"stage": "judge"}, complete=True)

        # Both filters applied: stage=gen AND status=completed
        runs = manager.list_runs(tags={"stage": "gen"}, status="completed")
        assert len(runs) == 1
        assert runs[0].run_id == "run-1"
