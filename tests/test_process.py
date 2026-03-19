"""Tests for Process — the user-facing run/resume/dry_run interface."""

import copy

import pytest

from parawave.decorator import parawave
from parawave.errors import DuplicateRunError, RunNotFoundError, ValidationError
from parawave.process import Process


class TestProcessRun:
    def test_basic_run(self):
        async def process(city: str) -> str:
            return f"processed {city}"

        proc = Process(func=process, config={})
        result = proc.run(data=[{"city": "NYC"}, {"city": "LA"}])

        assert result.ok is True
        assert len(result) == 2
        assert result[0].output == "processed NYC"
        assert result[1].output == "processed LA"

    def test_run_with_broadcast(self):
        async def process(city: str, model: str) -> dict:
            return {"city": city, "model": model}

        proc = Process(func=process, config={})
        result = proc.run(
            data=[{"city": "NYC"}, {"city": "LA"}],
            model="gpt-4",
        )

        assert result.ok is True
        assert result[0].output["model"] == "gpt-4"
        assert result[1].output["model"] == "gpt-4"

    def test_run_with_custom_run_id(self):
        async def process(city: str) -> str:
            return "ok"

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"city": "NYC"}], run_id="my-batch")

        assert result.run_id == "my-batch"

    def test_sync_function(self):
        def process(city: str) -> str:
            return f"processed {city}"

        proc = Process(func=process, config={})
        result = proc.run(data=[{"city": "NYC"}])

        assert result.ok is True
        assert result[0].output == "processed NYC"


class TestProcessDryRun:
    def test_dry_run(self):
        async def process(city: str) -> str:
            return f"processed {city}"

        proc = Process(func=process, config={})
        result = proc.dry_run(data=[{"city": "NYC"}])

        assert result.ok is True
        assert len(result) == 1
        assert result[0].output == "processed NYC"


class TestProcessResume:
    def test_resume_same_session(self):
        calls = {"n": 0}

        async def process(city: str) -> str:
            calls["n"] += 1
            if calls["n"] <= 1:
                raise ValueError("first call fails")
            return f"processed {city}"

        proc = Process(func=process, config={"storage": "in_memory"})
        result1 = proc.run(data=[{"city": "NYC"}])

        assert result1.ok is False

        # Resume retries the failed item
        result2 = proc.resume()
        assert result2.ok is True
        assert result2[0].output == "processed NYC"

    def test_resume_nonexistent_raises(self):
        async def process(city: str) -> str:
            return "ok"

        proc = Process(func=process, config={"storage": "in_memory"})
        with pytest.raises(RunNotFoundError):
            proc.resume("nonexistent-run-id")


class TestDuplicateRunId:
    def test_duplicate_user_run_id_raises(self):
        async def process(city: str) -> str:
            return "ok"

        proc = Process(func=process, config={"storage": "in_memory"})
        proc.run(data=[{"city": "NYC"}], run_id="my-batch")

        with pytest.raises(DuplicateRunError):
            proc.run(data=[{"city": "LA"}], run_id="my-batch")


class TestProcessConfig:
    def test_config_returns_dict(self):
        @parawave(max_concurrency=20, storage="in_memory")
        def fn(x): return x

        config = fn.config
        assert isinstance(config, dict)
        assert config["max_concurrency"] == 20

    def test_config_is_deep_copy(self):
        @parawave(on_start=[lambda r, t: None], storage="in_memory")
        def fn(x): return x

        config = fn.config
        config["on_start"].append(lambda r, t: None)
        assert len(fn.config["on_start"]) == 1


class TestValidateOverrides:
    def test_valid_override(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        fn._validate_overrides({"max_concurrency": 5})

    def test_unknown_key_raises(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        with pytest.raises(ValidationError, match="Unknown config keys"):
            fn._validate_overrides({"bogus": 123})

    def test_non_overridable_key_raises(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        with pytest.raises(ValidationError, match="Cannot override"):
            fn._validate_overrides({"storage": "sqlite"})

    def test_invalid_value_raises(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        with pytest.raises(ValidationError):
            fn._validate_overrides({"max_concurrency": 0})

    def test_hook_must_be_list(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        with pytest.raises(ValidationError, match="must be a list"):
            fn._validate_overrides({"on_retry": "not a list"})

    def test_hook_items_must_be_callable(self):
        @parawave(storage="in_memory")
        def fn(x): return x

        with pytest.raises(ValidationError, match="not callable"):
            fn._validate_overrides({"on_retry": [123]})


class TestRunWithOverrides:
    def test_run_with_concurrency_override(self):
        @parawave(max_concurrency=50, storage="in_memory")
        def fn(x): return x

        result = fn.run(data=[{"x": 1}], max_concurrency=2)
        assert result.ok

    def test_run_override_does_not_mutate_config(self):
        @parawave(max_concurrency=50, storage="in_memory")
        def fn(x): return x

        fn.run(data=[{"x": 1}], max_concurrency=2)
        assert fn.config["max_concurrency"] == 50

    def test_broadcast_still_works(self):
        @parawave(max_concurrency=5, storage="in_memory")
        def fn(x, y): return x + y

        result = fn.run(data=[{"x": 1}, {"x": 2}], y=10)
        assert result.ok
        assert result.data == [11, 12]

    def test_broadcast_and_override_together(self):
        @parawave(max_concurrency=50, storage="in_memory")
        def fn(x, y): return x + y

        result = fn.run(data=[{"x": 1}, {"x": 2}], y=10, max_concurrency=2)
        assert result.ok
        assert result.data == [11, 12]
        assert fn.config["max_concurrency"] == 50


class TestResumeWithOverrides:
    def test_resume_uses_stored_config(self):
        call_count = 0

        @parawave(max_concurrency=50, storage="in_memory")
        def fn(x):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise ValueError("fail")
            return x

        result = fn.run(data=[{"x": 1}, {"x": 2}])
        assert not result.ok

        result2 = fn.resume()
        assert result2.num_completed >= 1

    def test_resume_with_override(self):
        call_count = 0

        @parawave(max_concurrency=10, storage="in_memory")
        def fn(x):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise ValueError("fail first time")
            return x

        result = fn.run(data=[{"x": 1}])
        assert not result.ok

        result2 = fn.resume(max_concurrency=1)
        assert result2.ok


class TestProcessWarmup:
    def test_warmup_off_by_default(self):
        """Warmup is off by default — all items run concurrently."""
        async def process(x: int) -> int:
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": 1}, {"x": 2}, {"x": 3}])

        assert result.ok is True
        assert result.num_completed == 3

    def test_warmup_enabled_via_run(self):
        """warmup=True on .run() overrides the default."""
        async def process(x: int) -> int:
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": 1}, {"x": 2}], warmup=True)

        assert result.ok is True
        assert result.num_completed == 2

    def test_warmup_enabled_via_config(self):
        """warmup=True in config should work."""
        async def process(x: int) -> int:
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory", "warmup": True})
        result = proc.run(data=[{"x": 1}, {"x": 2}])

        assert result.ok is True
        assert result.num_completed == 2

    def test_warmup_catches_function_error(self):
        """Warmup failure should stop the run, not process all items."""
        call_count = {"n": 0}

        async def process(x: int) -> int:
            call_count["n"] += 1
            raise ValueError("broken function")

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": i} for i in range(10)], warmup=True)

        assert result.ok is False
        assert result[0].status == "failed"
        assert call_count["n"] == 1
        assert result.num_pending == 9

    def test_warmup_catches_output_serialization_error(self):
        """Warmup should catch non-serializable output before scaling up."""
        call_count = {"n": 0}

        async def process(x: int):
            call_count["n"] += 1
            return b"binary data"

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": i} for i in range(10)], warmup=True)

        assert result.ok is False
        assert result[0].status == "failed"
        assert "not JSON-serializable" in result[0].error
        assert call_count["n"] == 1
        assert result.num_pending == 9

    def test_warmup_on_resume(self):
        """warmup=True on .resume() should warmup with first retry item."""
        attempts = {"n": 0}

        async def process(x: int) -> int:
            attempts["n"] += 1
            if attempts["n"] <= 1:
                raise ValueError("first call fails")
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": 1}, {"x": 2}, {"x": 3}], warmup=True)
        assert result.ok is False

        result = proc.resume(warmup=True)
        assert result.ok is True
        assert result.num_completed == 3

    def test_resume_default_no_warmup(self):
        """resume() should not apply warmup by default."""
        attempts = {"n": 0}

        async def process(x: int) -> int:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("first call fails")
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.run(data=[{"x": 1}, {"x": 2}, {"x": 3}], warmup=True)
        assert result.ok is False

        result = proc.resume()
        assert result.ok is True
        assert result.num_completed == 3

    def test_dry_run_unaffected(self):
        """dry_run() should work as before."""
        async def process(x: int) -> int:
            return x * 2

        proc = Process(func=process, config={"storage": "in_memory"})
        result = proc.dry_run(data=[{"x": 1}])

        assert result.ok is True
        assert result[0].output == 2


class TestProcessInputValidation:
    def test_non_serializable_input_raises(self):
        """Non-serializable inputs should raise ValidationError before execution."""
        call_count = {"n": 0}

        async def process(data):
            call_count["n"] += 1
            return "ok"

        proc = Process(func=process, config={"storage": "in_memory"})
        with pytest.raises(ValidationError, match="not JSON-serializable"):
            proc.run(data=[{"data": b"binary"}])

        assert call_count["n"] == 0


class TestProcessTags:
    def test_run_accepts_tags(self):
        @parawave(storage="in_memory", progress=None)
        def echo(x):
            return x

        result = echo.run(
            data=[{"x": 1}],
            tags={"experiment": "v1"},
        )
        assert result.tags == {"experiment": "v1"}
        assert result.ok

    def test_run_without_tags(self):
        @parawave(storage="in_memory", progress=None)
        def echo(x):
            return x

        result = echo.run(data=[{"x": 1}])
        assert result.tags is None


class TestFuncName:
    def test_func_name_stored_on_run(self):
        """Run should store the function name."""
        import asyncio
        import parawave

        @parawave(storage="in_memory", progress=None)
        async def my_test_function(x: int) -> int:
            return x * 2

        result = my_test_function.run(data=[{"x": 1}])
        storage = my_test_function._shared_storage
        run = asyncio.run(storage.get_run(result.run_id))
        assert run.func_name == "TestFuncName.test_func_name_stored_on_run.<locals>.my_test_function"

    def test_run_info_summary_includes_func_name(self):
        """RunInfo.summary should display func_name."""
        from parawave.storage.models import RunInfo
        from datetime import datetime
        info = RunInfo(
            run_id="test", func_hash="abc123",
            status="completed", total_items=10, num_completed=10,
            num_failed=0, num_pending=0, num_retried=0, num_attempts=10,
            func_name="my_func", tags=None,
            created_at=datetime.now(), elapsed=5.0,
        )
        assert "my_func" in info.summary

    def test_run_info_summary_falls_back_to_hash(self):
        """RunInfo.summary should use func_hash prefix when func_name is empty."""
        from parawave.storage.models import RunInfo
        from datetime import datetime
        info = RunInfo(
            run_id="test", func_hash="abc12345deadbeef",
            status="completed", total_items=10, num_completed=10,
            num_failed=0, num_pending=0, num_retried=0, num_attempts=10,
            func_name="", tags=None,
            created_at=datetime.now(), elapsed=5.0,
        )
        assert "abc12345" in info.summary


class TestProcessResumeTags:
    def test_resume_preserves_tags(self):
        @parawave(storage="in_memory", progress=None)
        def fail_first(x):
            if not hasattr(fail_first, '_called'):
                fail_first._called = True
                raise ValueError("fail")
            return x

        result = fail_first.run(
            data=[{"x": 1}],
            tags={"experiment": "v1"},
        )
        assert not result.ok
        assert result.tags == {"experiment": "v1"}

        resumed = fail_first.resume()
        assert resumed.tags == {"experiment": "v1"}
        assert resumed.elapsed > 0
