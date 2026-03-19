"""Tests for code review fixes: config serialization, SIGTERM, progress counters,
RunNotFoundError message, and @parawave without parentheses."""

import json
import signal
import pytest

from parawave.errors import RunNotFoundError
from parawave.retry import RetryPolicy
from parawave.shutdown import ShutdownHandler
from parawave.storage.sqlite.sqlite import _ConfigEncoder


class TestConfigEncoder:
    """Test that _ConfigEncoder handles non-JSON-serializable config objects."""

    def test_retry_policy_serializes(self):
        policy = RetryPolicy(max_retries=3, backoff="exponential", base_delay=1.0, max_delay=60.0)
        config = {"retry": policy, "max_concurrency": 10}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["retry"]["max_retries"] == 3
        assert parsed["retry"]["backoff"] == "exponential"
        assert parsed["retry"]["base_delay"] == 1.0
        assert parsed["retry"]["max_delay"] == 60.0
        assert parsed["max_concurrency"] == 10

    def test_retry_policy_with_retryable_exceptions(self):
        policy = RetryPolicy(max_retries=2, retryable=[ValueError, TimeoutError])
        config = {"retry": policy}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["retry"]["retryable"] == ["ValueError", "TimeoutError"]
        assert parsed["retry"]["non_retryable"] is None

    def test_retry_policy_with_non_retryable_exceptions(self):
        policy = RetryPolicy(max_retries=2, non_retryable=[KeyError])
        config = {"retry": policy}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["retry"]["non_retryable"] == ["KeyError"]
        assert parsed["retry"]["retryable"] is None

    def test_callable_hooks_serialize(self):
        def my_hook(result):
            pass

        config = {"on_start": [my_hook], "on_complete": [my_hook]}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["on_start"] == ["<my_hook>"]
        assert parsed["on_complete"] == ["<my_hook>"]

    def test_none_retry_serializes(self):
        config = {"retry": None, "max_concurrency": 5}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["retry"] is None

    def test_plain_values_pass_through(self):
        config = {"max_concurrency": 10, "rate_limit": 100, "task_timeout": 60.0}
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed == config

    def test_full_config_serializes(self):
        """Simulate the full config dict that process.py passes to storage."""
        def on_start_hook(run_id, total):
            pass

        config = {
            "max_concurrency": 10,
            "rate_limit": 100,
            "rate_period": 60,
            "retry": RetryPolicy(max_retries=3, retryable=[ValueError]),
            "executor": "auto",
            "task_timeout": 60,
            "stop_on_consecutive_failures": 5,
            "progress": "console",
            "on_start": [on_start_hook],
            "on_item_complete": [],
            "on_item_error": [],
            "on_complete": [],
        }
        # Should not raise
        result = json.dumps(config, cls=_ConfigEncoder)
        parsed = json.loads(result)
        assert parsed["retry"]["max_retries"] == 3
        assert parsed["on_start"] == ["<on_start_hook>"]


class TestConfigSerializationWithSqliteStorage:
    """Integration test: ensure sqlite storage can store config with RetryPolicy."""

    @pytest.mark.asyncio
    async def test_create_run_with_retry_policy(self, tmp_path):
        from parawave.storage.sqlite.sqlite import SqliteStore

        store = SqliteStore(tmp_path / "test.db")
        await store.initialize()

        config = {
            "max_concurrency": 10,
            "retry": RetryPolicy(max_retries=3, backoff="exponential"),
            "on_start": [],
        }
        await store.create_run("run-test", config, "abc123", 5)

        run = await store.get_run("run-test")
        assert run.run_id == "run-test"
        assert run.config["retry"]["max_retries"] == 3
        assert run.config["retry"]["backoff"] == "exponential"

        await store.close()

    @pytest.mark.asyncio
    async def test_create_run_with_hooks_and_retry(self, tmp_path):
        from parawave.storage.sqlite.sqlite import SqliteStore

        def my_hook():
            pass

        store = SqliteStore(tmp_path / "test.db")
        await store.initialize()

        config = {
            "max_concurrency": 5,
            "retry": RetryPolicy(max_retries=2, non_retryable=[ValueError]),
            "on_start": [my_hook],
            "on_complete": [my_hook],
        }
        await store.create_run("run-hooks", config, "def456", 3)

        run = await store.get_run("run-hooks")
        assert run.config["retry"]["non_retryable"] == ["ValueError"]
        assert run.config["on_start"] == ["<my_hook>"]

        await store.close()


class TestSIGTERMHandling:
    """Test that ShutdownHandler handles SIGTERM in addition to SIGINT."""

    def test_sigterm_triggers_graceful_shutdown(self):
        handler = ShutdownHandler()
        # Simulate SIGTERM signal
        handler.request_shutdown()
        assert handler.should_stop is True
        assert handler.force_stop is False

    def test_install_sets_sigterm_handler(self):
        handler = ShutdownHandler()
        original_sigterm = signal.getsignal(signal.SIGTERM)
        try:
            handler.install()
            # SIGTERM handler should now be our handler
            current = signal.getsignal(signal.SIGTERM)
            assert current == handler._handle_signal
        finally:
            handler.uninstall()

        # After uninstall, original handler should be restored
        assert signal.getsignal(signal.SIGTERM) == original_sigterm


class TestRunNotFoundErrorMessage:
    """Test that RunNotFoundError produces clear messages."""

    def test_default_message(self):
        err = RunNotFoundError("run-abc123")
        assert str(err) == "Run not found: run-abc123"
        assert err.run_id == "run-abc123"

    def test_custom_message(self):
        err = RunNotFoundError(
            run_id="<none>",
            message="No previous run to resume. Call .resume('run-id') with a specific run ID.",
        )
        assert "No previous run to resume" in str(err)
        assert "Run not found" not in str(err)

    def test_resume_without_run_id_raises_clear_message(self):
        from parawave.decorator import parawave

        @parawave(storage="in_memory", progress=None)
        async def process(x: int) -> int:
            return x

        with pytest.raises(RunNotFoundError, match="No previous run to resume"):
            process.resume()


class TestParawaveWithoutParentheses:
    """Test that @parawave without () gives a clear error."""

    def test_without_parens_raises_type_error(self):
        import parawave

        with pytest.raises(TypeError, match="Use @parawave\\(\\) with parentheses"):

            @parawave
            def process(x: int) -> int:
                return x

    def test_with_parens_works(self):
        import parawave

        @parawave(storage="in_memory", progress=None)
        def process(x: int) -> int:
            return x

        assert hasattr(process, "run")


class TestProgressCounters:
    """Test that progress snapshots use O(1) counters correctly."""

    @pytest.mark.asyncio
    async def test_progress_counts_match_results(self):
        """Run engine directly with a capturing progress to verify counter accuracy."""
        from parawave.engine import Engine, EngineConfig
        from parawave.progress.base import ProgressSnapshot
        from parawave.storage.memory import InMemoryStorage

        snapshots = []

        class CapturingProgress:
            def on_update(self, snapshot: ProgressSnapshot) -> None:
                snapshots.append(snapshot)

        def process(x: int) -> int:
            if x == 2:
                raise ValueError("fail")
            return x * 10

        storage = InMemoryStorage()
        config = EngineConfig(
            max_concurrency=1,
            progress=CapturingProgress(),
        )
        items = [{"x": 1}, {"x": 2}, {"x": 3}]
        engine = Engine(
            func=process,
            is_async=False,
            items=items,
            config=config,
            storage=storage,
        )

        await storage.create_run(engine.run_id, {}, "test", items)
        result = await engine.run()

        assert result.ok is False
        assert len(result.completed) == 2
        assert len(result.failed) == 1

        # The last snapshot should have accurate counts from O(1) counters
        assert len(snapshots) == 3
        final = snapshots[-1]
        assert final.completed == 2
        assert final.failed == 1
        assert final.total == 3
        assert final.pending == 0
