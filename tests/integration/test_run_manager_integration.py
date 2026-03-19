"""Integration test: run with tags -> browse via RunManager -> load results."""

import parawave
from parawave import RunManager
from parawave.storage.sqlite import SqliteStorage


class TestRunManagerIntegration:
    def test_full_workflow(self, tmp_path):
        db_path = tmp_path / ".parawave"

        @parawave(storage="sqlite", progress=None)
        def double(x: int) -> int:
            return x * 2

        # Patch storage path for test isolation
        double._create_storage = lambda: SqliteStorage(db_path)

        result = double.run(
            data=[{"x": i} for i in range(5)],
            tags={"experiment": "test", "stage": "double"},
        )
        assert result.ok
        assert result.tags == {"experiment": "test", "stage": "double"}
        run_id = result.run_id

        # Browse via RunManager
        manager = RunManager("sqlite", path=str(db_path))
        runs = manager.list_runs()
        assert len(runs) == 1

        info = manager.get(run_id)
        assert info.status == "completed"
        assert info.num_completed == 5
        assert info.tags == {"experiment": "test", "stage": "double"}
        assert info.elapsed > 0

        # Filter
        found = manager.list_runs(tags={"stage": "double"})
        assert len(found) == 1
        not_found = manager.list_runs(tags={"stage": "triple"})
        assert len(not_found) == 0

        # Load full results
        loaded = manager.load(run_id)
        assert len(loaded) == 5
        assert loaded.data == [0, 2, 4, 6, 8]
        assert loaded.tags == {"experiment": "test", "stage": "double"}

        # Update tags
        manager.update_tags(run_id, {"experiment": "test", "quality": "good"})
        info = manager.get(run_id)
        assert info.tags == {"experiment": "test", "quality": "good"}

        # Delete
        manager.delete(run_id)
        assert manager.list_runs() == []
