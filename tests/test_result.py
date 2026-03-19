"""Tests for Result and ResultItem."""

import pytest

from parawave.result import Result, ResultItem


class TestResultItem:
    def test_completed_item(self):
        item = ResultItem(index=0, input={"city": "NYC"}, output="processed NYC", status="completed", error=None)
        assert item.ok is True
        assert item.output == "processed NYC"
        assert item.error is None
        assert item.index == 0

    def test_failed_item(self):
        item = ResultItem(index=1, input={"city": "LA"}, output=None, status="failed", error="API timeout")
        assert item.ok is False
        assert item.output is None
        assert item.error == "API timeout"

    def test_pending_item(self):
        item = ResultItem(index=2, input={"city": "Tokyo"}, output=None, status="pending", error=None)
        assert item.ok is False
        assert item.output is None
        assert item.error is None


class TestResult:
    @pytest.fixture
    def mixed_result(self) -> Result:
        items = [
            ResultItem(index=0, input={"city": "NYC"}, output="ok", status="completed", error=None),
            ResultItem(index=1, input={"city": "LA"}, output=None, status="failed", error="RuntimeError: test error"),
            ResultItem(index=2, input={"city": "Tokyo"}, output="ok", status="completed", error=None),
            ResultItem(index=3, input={"city": "London"}, output=None, status="pending", error=None),
        ]
        return Result(items=items, run_id="test-run-1")

    @pytest.fixture
    def all_completed(self) -> Result:
        items = [
            ResultItem(index=i, input={"city": f"city_{i}"}, output=f"ok_{i}", status="completed", error=None)
            for i in range(3)
        ]
        return Result(items=items, run_id="test-run-2")

    def test_ok_all_completed(self, all_completed: Result):
        assert all_completed.ok is True

    def test_ok_mixed(self, mixed_result: Result):
        assert mixed_result.ok is False

    def test_run_id(self, mixed_result: Result):
        assert mixed_result.run_id == "test-run-1"

    def test_len(self, mixed_result: Result):
        assert len(mixed_result) == 4

    def test_summary_all_completed(self, all_completed: Result):
        assert all_completed.summary == "3/3 completed"

    def test_summary_mixed(self, mixed_result: Result):
        summary = mixed_result.summary
        assert "2/4 completed" in summary
        assert "1 failed" in summary
        assert "1 pending" in summary

    def test_data_property(self, mixed_result: Result):
        data = mixed_result.data
        assert data == ["ok", None, "ok", None]

    def test_completed_filter(self, mixed_result: Result):
        completed = mixed_result.completed
        assert len(completed) == 2
        assert all(item.ok for item in completed)

    def test_failed_filter(self, mixed_result: Result):
        failed = mixed_result.failed
        assert len(failed) == 1
        assert failed[0].index == 1

    def test_pending_filter(self, mixed_result: Result):
        pending = mixed_result.pending
        assert len(pending) == 1
        assert pending[0].index == 3

    def test_getitem_by_index(self, mixed_result: Result):
        item = mixed_result[0]
        assert item.index == 0
        assert item.input == {"city": "NYC"}

    def test_getitem_by_slice(self, mixed_result: Result):
        batch = mixed_result[1:3]
        assert len(batch) == 2
        assert batch[0].index == 1
        assert batch[1].index == 2

    def test_iter(self, mixed_result: Result):
        indices = [item.index for item in mixed_result]
        assert indices == [0, 1, 2, 3]

    def test_empty_result(self):
        result = Result(items=[], run_id="empty")
        assert result.ok is True
        assert len(result) == 0
        assert result.data == []
        assert result.summary == "0/0 completed"

    def test_summary_with_failures_and_pending(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None),
            ResultItem(index=1, input={}, output=None, status="failed", error="RuntimeError: test error"),
            ResultItem(index=2, input={}, output=None, status="pending", error=None),
        ]
        result = Result(items=items, run_id="test")
        summary = result.summary
        assert "1/3 completed" in summary
        assert "1 failed" in summary
        assert "1 pending" in summary


class TestResultCounts:
    def test_num_completed(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None),
            ResultItem(index=1, input={}, output=None, status="failed", error="RuntimeError: err"),
            ResultItem(index=2, input={}, output="ok", status="completed", error=None),
        ]
        result = Result(items=items, run_id="test")
        assert result.num_completed == 2
        assert result.num_failed == 1
        assert result.num_pending == 0

    def test_num_pending(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None),
            ResultItem(index=1, input={}, output=None, status="pending", error=None),
        ]
        result = Result(items=items, run_id="test")
        assert result.num_pending == 1

    def test_num_retried_and_attempts(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=3),
            ResultItem(index=2, input={}, output=None, status="failed", error="RuntimeError: err", attempts=4),
        ]
        result = Result(items=items, run_id="test")
        assert result.num_retried == 2   # items 1 and 2 had attempts > 1
        assert result.num_attempts == 8  # 1 + 3 + 4

    def test_num_retried_zero_when_no_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=1),
        ]
        result = Result(items=items, run_id="test")
        assert result.num_retried == 0
        assert result.num_attempts == 2


class TestSummaryFormat:
    def test_all_completed_no_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=1),
        ]
        result = Result(items=items, run_id="test")
        assert result.summary == "2/2 completed"

    def test_failures_no_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output=None, status="failed", error="RuntimeError: err", attempts=1),
        ]
        result = Result(items=items, run_id="test")
        assert result.summary == "1/2 completed | 1 failed"

    def test_with_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=3),
            ResultItem(index=2, input={}, output=None, status="failed", error="RuntimeError: err", attempts=2),
        ]
        result = Result(items=items, run_id="test")
        summary = result.summary
        assert summary.startswith("2/3 completed")
        assert "6 attempts" in summary
        assert "2 completed" in summary
        assert "2 retried" in summary
        assert "1 failed" in summary

    def test_with_pending_and_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=2),
            ResultItem(index=1, input={}, output=None, status="failed", error="RuntimeError: err", attempts=3),
            ResultItem(index=2, input={}, output=None, status="pending", error=None, attempts=1),
        ]
        result = Result(items=items, run_id="test")
        summary = result.summary
        assert summary.startswith("1/3 completed")
        assert "1 failed" in summary
        assert "1 pending" in summary
        assert "6 attempts" in summary
        assert "2 retried" in summary

    def test_with_elapsed_time(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=1),
        ]
        result = Result(items=items, run_id="test", elapsed=2.5)
        assert result.elapsed == 2.5
        assert result.items_per_second == 2 / 2.5  # 0.8
        summary = result.summary
        assert "2.5s" in summary
        assert "items/s" in summary

    def test_with_elapsed_and_retries(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None, attempts=1),
            ResultItem(index=1, input={}, output="ok", status="completed", error=None, attempts=3),
            ResultItem(index=2, input={}, output=None, status="failed", error="RuntimeError: err", attempts=2),
        ]
        result = Result(items=items, run_id="test", elapsed=5.0)
        summary = result.summary
        # Should have: headline | details | elapsed | throughput
        assert summary.startswith("2/3 completed")
        assert "6 attempts" in summary
        assert "5.0s" in summary
        assert "items/s" in summary
        assert "1 failed" in summary

    def test_zero_elapsed_no_timing(self):
        items = [
            ResultItem(index=0, input={}, output="ok", status="completed", error=None),
        ]
        result = Result(items=items, run_id="test", elapsed=0.0)
        assert result.items_per_second == 0.0
        assert "items/s" not in result.summary


class TestResultItemElapsed:
    def test_elapsed_default(self):
        item = ResultItem(index=0, input={}, output="ok", status="completed", error=None)
        assert item.elapsed == 0.0

    def test_elapsed_set(self):
        item = ResultItem(index=0, input={}, output="ok", status="completed", error=None, elapsed=2.5)
        assert item.elapsed == 2.5

    def test_elapsed_in_to_dict(self):
        item = ResultItem(index=0, input={}, output="ok", status="completed", error=None, elapsed=1.3)
        d = item.to_dict()
        assert d["elapsed"] == 1.3


class TestResultTags:
    def test_tags_default_none(self):
        result = Result(items=[], run_id="run-1")
        assert result.tags is None

    def test_tags_set(self):
        result = Result(items=[], run_id="run-1",
                        tags={"experiment": "v1"})
        assert result.tags == {"experiment": "v1"}

    def test_tags_in_to_dict(self):
        result = Result(items=[], run_id="run-1",
                        tags={"stage": "generate"})
        d = result.to_dict()
        assert d["tags"] == {"stage": "generate"}


class TestAvgItemElapsed:
    def test_avg_item_elapsed(self):
        items = [
            ResultItem(index=0, input={}, output="a", status="completed", error=None, elapsed=1.0),
            ResultItem(index=1, input={}, output="b", status="completed", error=None, elapsed=3.0),
        ]
        result = Result(items=items, run_id="r1")
        assert result.avg_item_elapsed == 2.0

    def test_avg_item_elapsed_excludes_failed(self):
        items = [
            ResultItem(index=0, input={}, output="a", status="completed", error=None, elapsed=2.0),
            ResultItem(index=1, input={}, output=None, status="failed", error="err", elapsed=1.0),
        ]
        result = Result(items=items, run_id="r1")
        assert result.avg_item_elapsed == 2.0

    def test_avg_item_elapsed_no_completed(self):
        items = [
            ResultItem(index=0, input={}, output=None, status="failed", error="err", elapsed=1.0),
        ]
        result = Result(items=items, run_id="r1")
        assert result.avg_item_elapsed == 0.0
