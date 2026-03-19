"""Tests for second-pass code review fixes: hook safety, decorator validation,
data type check, JSONL crash resilience, shutdown_timeout removal."""

import json
import logging
from functools import partial
from pathlib import Path

import pytest

from parawave.errors import ValidationError
from parawave.hooks import fire_hooks
from parawave.result import ResultItem


class TestHookCallableObjects:
    """Test that fire_hooks handles callable class instances, lambdas, and partials."""

    def test_callable_class_instance_hook_error_swallowed(self, caplog):
        """A callable class instance that raises should not crash fire_hooks."""

        class MyTracker:
            def __call__(self, run_id, total):
                raise RuntimeError("tracker failed")

        with caplog.at_level(logging.WARNING):
            fire_hooks([MyTracker()], "run-1", 10)
        assert "tracker failed" in caplog.text

    def test_lambda_hook_error_swallowed(self, caplog):
        """A lambda hook that raises should not crash fire_hooks."""
        bad_lambda = lambda run_id, total: 1 / 0  # noqa: E731
        with caplog.at_level(logging.WARNING):
            fire_hooks([bad_lambda], "run-1", 10)
        assert "ZeroDivisionError" in caplog.text

    def test_partial_hook_error_swallowed(self, caplog):
        """A functools.partial hook that raises should not crash fire_hooks."""

        def failing_hook(prefix, run_id, total):
            raise ValueError(f"{prefix} failed")

        with caplog.at_level(logging.WARNING):
            fire_hooks([partial(failing_hook, "test")], "run-1", 10)
        assert "test failed" in caplog.text

    def test_callable_instance_hook_succeeds(self):
        """A callable class instance that works should fire normally."""
        calls = []

        class Tracker:
            def __call__(self, item: ResultItem):
                calls.append(item.index)

        item = ResultItem(index=3, input={}, output="ok", status="completed", error=None)
        fire_hooks([Tracker()], item)
        assert calls == [3]

    def test_mixed_hooks_continue_after_error(self):
        """After a callable instance hook fails, subsequent hooks should still fire."""
        calls = []

        class BadTracker:
            def __call__(self, run_id, total):
                raise RuntimeError("fail")

        def good_hook(run_id, total):
            calls.append("good")

        fire_hooks([BadTracker(), good_hook], "run-1", 10)
        assert calls == ["good"]


class TestDecoratorParameterValidation:
    """Test that invalid decorator params are caught at decoration time."""

    def test_max_concurrency_zero_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="max_concurrency must be >= 1"):
            @parawave(max_concurrency=0)
            def process(x: int) -> int:
                return x

    def test_max_concurrency_negative_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="max_concurrency must be >= 1"):
            @parawave(max_concurrency=-5)
            def process(x: int) -> int:
                return x

    def test_task_timeout_zero_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="task_timeout must be > 0"):
            @parawave(task_timeout=0)
            def process(x: int) -> int:
                return x

    def test_task_timeout_negative_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="task_timeout must be > 0"):
            @parawave(task_timeout=-1)
            def process(x: int) -> int:
                return x

    def test_rate_limit_zero_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="rate_limit must be > 0"):
            @parawave(rate_limit=0)
            def process(x: int) -> int:
                return x

    def test_rate_period_zero_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="rate_period must be > 0"):
            @parawave(rate_period=0)
            def process(x: int) -> int:
                return x

    def test_stop_on_consecutive_failures_zero_raises(self):
        from parawave.decorator import parawave

        with pytest.raises(ValidationError, match="stop_on_consecutive_failures must be >= 1"):
            @parawave(stop_on_consecutive_failures=0)
            def process(x: int) -> int:
                return x

    def test_invalid_storage_type_raises_at_runtime(self):
        from parawave.decorator import parawave

        @parawave(storage="postgres")
        def process(x: int) -> int:
            return x

        with pytest.raises(ValueError, match="Unknown storage"):
            process.run(data=[{"x": 1}])

    def test_valid_params_pass(self):
        from parawave.decorator import parawave
        from parawave.process import Process

        @parawave(
            max_concurrency=1,
            task_timeout=30,
            rate_limit=100,
            rate_period=60,
            stop_on_consecutive_failures=5,
            storage="in_memory",
            progress=None,
        )
        def process(x: int) -> int:
            return x

        assert isinstance(process, Process)

    def test_shutdown_timeout_param_removed(self):
        """shutdown_timeout should no longer be accepted."""
        from parawave.decorator import parawave

        with pytest.raises(TypeError, match="shutdown_timeout"):
            @parawave(shutdown_timeout=30)
            def process(x: int) -> int:
                return x


class TestDataTypeValidation:
    """Test that non-list data is rejected with a clear error."""

    def test_string_data_raises(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x

        with pytest.raises(ValidationError, match="data must be a list"):
            process.run(data="hello")

    def test_int_data_raises(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x

        with pytest.raises(ValidationError, match="data must be a list"):
            process.run(data=123)

    def test_none_data_raises(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x

        with pytest.raises(ValidationError, match="data must be a list"):
            process.run(data=None)

    def test_dict_data_raises(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x

        with pytest.raises(ValidationError, match="data must be a list"):
            process.run(data={"x": 1})

    def test_list_of_dicts_passes(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x * 10

        result = process.run(data=[{"x": 1}, {"x": 2}])
        assert result.ok is True


class TestJsonlCrashResilience:
    """Test that corrupt JSONL lines are handled gracefully."""

    @pytest.mark.asyncio
    async def test_read_output_skips_corrupt_lines(self, tmp_path):
        from parawave.storage.sqlite.jsonl import JsonlStore

        store = JsonlStore(tmp_path / "test_run")
        (tmp_path / "test_run").mkdir()

        # Write valid output, then a corrupt line, then another valid output
        outputs_path = tmp_path / "test_run" / "outputs.jsonl"
        outputs_path.write_text(
            json.dumps({"index": 0, "data": "first"}) + "\n"
            + "THIS IS CORRUPT JSON\n"
            + json.dumps({"index": 1, "data": "second"}) + "\n"
        )

        # Should read valid entries without crashing
        assert await store.read_output(0) == "first"
        assert await store.read_output(1) == "second"

    @pytest.mark.asyncio
    async def test_read_output_handles_empty_lines(self, tmp_path):
        from parawave.storage.sqlite.jsonl import JsonlStore

        store = JsonlStore(tmp_path / "test_run")
        (tmp_path / "test_run").mkdir()

        outputs_path = tmp_path / "test_run" / "outputs.jsonl"
        outputs_path.write_text(
            json.dumps({"index": 0, "data": "hello"}) + "\n"
            + "\n"
            + "\n"
        )

        assert await store.read_output(0) == "hello"

    @pytest.mark.asyncio
    async def test_read_output_handles_truncated_json(self, tmp_path):
        from parawave.storage.sqlite.jsonl import JsonlStore

        store = JsonlStore(tmp_path / "test_run")
        (tmp_path / "test_run").mkdir()

        # Simulate a crash mid-write — truncated JSON
        outputs_path = tmp_path / "test_run" / "outputs.jsonl"
        outputs_path.write_text(
            json.dumps({"index": 0, "data": "valid"}) + "\n"
            + '{"index": 1, "dat'  # truncated
        )

        assert await store.read_output(0) == "valid"
        assert await store.read_output(1) is None  # corrupt entry skipped
