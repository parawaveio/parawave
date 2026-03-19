"""Tests for storage data models."""

from datetime import datetime, timezone

from parawave.storage.models import RunRecord, ItemRecord, RunInfo


class TestRunRecord:
    def test_construction(self):
        record = RunRecord(
            run_id="run-abc123",
            func_hash="sha256:abcdef",
            config={"max_concurrency": 10},
            total_items=100,
        )
        assert record.run_id == "run-abc123"
        assert record.func_hash == "sha256:abcdef"
        assert record.config == {"max_concurrency": 10}
        assert record.total_items == 100


class TestItemRecord:
    def test_completed_item(self):
        record = ItemRecord(
            run_id="run-abc",
            index=0,
            status="completed",
            input_hash="sha256:111",
            error=None,
        )
        assert record.run_id == "run-abc"
        assert record.index == 0
        assert record.status == "completed"
        assert record.error is None

    def test_failed_item(self):
        record = ItemRecord(
            run_id="run-abc",
            index=1,
            status="failed",
            input_hash="sha256:222",
            error="ValueError: bad input",
        )
        assert record.status == "failed"
        assert record.error == "ValueError: bad input"


class TestItemRecordElapsed:
    def test_item_record_has_elapsed_default(self):
        record = ItemRecord(run_id="run-1", index=0, status="pending", input_hash="abc", error=None)
        assert record.elapsed == 0.0

    def test_item_record_elapsed_set(self):
        record = ItemRecord(run_id="run-1", index=0, status="completed", input_hash="abc", error=None, attempts=2, elapsed=1.5)
        assert record.elapsed == 1.5


class TestRunRecordNewFields:
    def test_defaults(self):
        record = RunRecord(run_id="run-1", func_hash="h", config={}, total_items=10)
        assert record.tags is None
        assert record.created_at == ""
        assert record.elapsed == 0.0
        assert record.status == "running"

    def test_with_all_fields(self):
        record = RunRecord(
            run_id="run-1", func_hash="h", config={}, total_items=10,
            tags={"stage": "generate"}, created_at="2026-03-16T21:00:00+00:00",
            elapsed=142.3, status="completed",
        )
        assert record.tags == {"stage": "generate"}
        assert record.status == "completed"
        assert record.elapsed == 142.3


class TestRunInfo:
    def _make_info(self, **overrides):
        defaults = dict(
            run_id="run-1", func_hash="h", status="completed", total_items=100,
            num_completed=95, num_failed=5, num_pending=0,
            num_retried=10, num_attempts=110,
            tags={"experiment": "v1"}, created_at=datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc),
            elapsed=50.0,
        )
        defaults.update(overrides)
        return RunInfo(**defaults)

    def test_items_per_second(self):
        info = self._make_info(num_completed=100, elapsed=50.0)
        assert info.items_per_second == 2.0

    def test_items_per_second_zero_elapsed(self):
        info = self._make_info(elapsed=0.0)
        assert info.items_per_second == 0.0

    def test_progress(self):
        info = self._make_info(num_completed=50, total_items=200)
        assert info.progress == "50/200 (25.0%)"

    def test_progress_zero_items(self):
        info = self._make_info(total_items=0, num_completed=0)
        assert info.progress == "0/0 (0.0%)"

    def test_summary_clean_run(self):
        info = self._make_info(
            num_completed=100, num_failed=0, num_pending=0,
            num_retried=0, num_attempts=100, total_items=100, elapsed=10.0,
        )
        assert "100/100 completed" in info.summary
        assert "10.0s" in info.summary
        assert "10.0 items/s" in info.summary

    def test_summary_with_failures(self):
        info = self._make_info(
            num_completed=95, num_failed=5, num_pending=0,
            num_retried=0, num_attempts=100, total_items=100, elapsed=10.0,
        )
        assert "95/100 completed" in info.summary
        assert "5 failed" in info.summary

    def test_summary_with_retries(self):
        info = self._make_info(
            num_completed=100, num_failed=0, num_pending=0,
            num_retried=10, num_attempts=115, total_items=100, elapsed=10.0,
        )
        assert "115 attempts" in info.summary
        assert "10 retried" in info.summary
