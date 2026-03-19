"""Process — user-facing interface for run, resume, dry_run."""

from __future__ import annotations

import copy
import hashlib
import inspect
from parawave.log import get_logger
from parawave._event_loop import run_in_event_loop
from typing import Any, Callable

from parawave.engine import Engine, EngineConfig
from parawave.errors import DuplicateRunError, RunNotFoundError, ValidationError
from parawave.progress.bar import create_bar_progress
from parawave.progress.console import ConsoleProgress
from parawave.result import Result, ResultItem
from parawave.retry import RetryPolicy
from parawave.storage.base import Storage
from parawave.storage.memory import InMemoryStorage
from parawave.validation import validate_inputs, validate_input_serializability

logger = get_logger(__name__)

_OVERRIDABLE = {
    "max_concurrency", "rate_limit", "rate_period", "task_timeout", "run_timeout",
    "retry", "stop_on_consecutive_failures", "progress",
    "on_start", "on_retry", "on_item_complete", "on_item_error", "on_complete",
    "warmup",
}

_NOT_OVERRIDABLE = {
    "storage",
    "executor",
}


class Process:
    """User-facing process created by the @parawave() decorator.

    Provides .run(), .resume(), and .dry_run() methods.
    """

    def __init__(self, func: Callable, config: dict[str, Any]) -> None:
        self._func = func
        self._config = config
        self._is_async = inspect.iscoroutinefunction(func)
        self._func_hash = self._compute_func_hash(func)
        self._last_run_id: str | None = None
        # For in-memory storage, keep a persistent instance so resume() can
        # access data written during run().
        self._shared_storage: Storage | None = None

        # Preserve function metadata
        self.__name__ = getattr(func, "__name__", "process")
        self.__doc__ = getattr(func, "__doc__", None)

    @property
    def config(self) -> dict[str, Any]:
        """Read-only view of current configuration."""
        return copy.deepcopy(self._config)

    def _validate_overrides(self, overrides: dict) -> dict:
        unknown = set(overrides) - _OVERRIDABLE - _NOT_OVERRIDABLE
        if unknown:
            raise ValidationError(f"Unknown config keys: {unknown}")

        blocked = set(overrides) & _NOT_OVERRIDABLE
        if blocked:
            raise ValidationError(
                f"Cannot override {blocked} at runtime. "
                f"These must be set in the @parawave() decorator."
            )

        hook_keys = {"on_start", "on_item_complete", "on_item_error", "on_retry", "on_complete"}
        for key in hook_keys & set(overrides):
            if not isinstance(overrides[key], list):
                raise ValidationError(f"{key} must be a list of callables")
            for i, fn in enumerate(overrides[key]):
                if not callable(fn):
                    raise ValidationError(f"{key}[{i}] is not callable")

        if "max_concurrency" in overrides and overrides["max_concurrency"] < 1:
            raise ValidationError("max_concurrency must be >= 1")
        if "task_timeout" in overrides and overrides["task_timeout"] <= 0:
            raise ValidationError("task_timeout must be > 0")
        if "run_timeout" in overrides and overrides["run_timeout"] is not None and overrides["run_timeout"] <= 0:
            raise ValidationError("run_timeout must be > 0")
        if "rate_limit" in overrides and overrides["rate_limit"] is not None and overrides["rate_limit"] <= 0:
            raise ValidationError("rate_limit must be > 0")
        if "rate_period" in overrides and overrides["rate_period"] <= 0:
            raise ValidationError("rate_period must be > 0")
        if "stop_on_consecutive_failures" in overrides and overrides["stop_on_consecutive_failures"] is not None and overrides["stop_on_consecutive_failures"] < 1:
            raise ValidationError("stop_on_consecutive_failures must be >= 1")

        return overrides

    def _split_kwargs(self, kwargs: dict) -> tuple[dict, dict]:
        """Split kwargs into config overrides and broadcast data."""
        overrides = {}
        broadcast = {}
        for key, value in kwargs.items():
            if key in _OVERRIDABLE or key in _NOT_OVERRIDABLE:
                overrides[key] = value
            else:
                broadcast[key] = value
        return overrides, broadcast

    def run(self, data: list[dict], *, run_id: str | None = None, tags: dict[str, str] | None = None, **kwargs) -> Result:
        """Execute all items in parallel. Returns Result."""
        overrides, broadcast = self._split_kwargs(kwargs)
        validated = self._validate_overrides(overrides)
        effective_config = {**self._config, **validated}

        merged = validate_inputs(self._func, data, broadcast)
        validate_input_serializability(merged)

        storage = self._create_storage()
        engine_config = self._build_engine_config_from(effective_config, len(merged))

        engine = Engine(
            func=self._func,
            is_async=self._is_async,
            items=merged,
            config=engine_config,
            storage=storage,
            run_id=run_id,
            tags=tags,
        )

        result = run_in_event_loop(self._execute_run(engine, storage, merged, effective_config, tags=tags))
        self._last_run_id = result.run_id

        if not result.ok:
            import sys
            print(
                f"[parawave] To resume: .resume() | Cross-session: .resume(\"{result.run_id}\")",
                file=sys.stderr, flush=True,
            )

        return result

    def dry_run(self, data: list[dict], **broadcast: Any) -> Result:
        """Run items with in-memory storage, no persistence."""
        merged = validate_inputs(self._func, data, broadcast)

        storage = InMemoryStorage()
        engine_config = self._build_engine_config(len(merged))
        engine_config.retry_policy = None
        engine_config.rate_limit = None
        engine_config.stop_on_consecutive_failures = None

        engine = Engine(
            func=self._func,
            is_async=self._is_async,
            items=merged,
            config=engine_config,
            storage=storage,
        )

        return run_in_event_loop(self._execute_run(engine, storage, merged, self._config))

    def resume(self, run_id: str | None = None, **overrides) -> Result:
        """Resume a previous run, retrying failed and pending items."""
        validated = self._validate_overrides(overrides)

        target_id = run_id or self._last_run_id
        if target_id is None:
            raise RunNotFoundError(
                run_id="<none>",
                message="No previous run to resume. Call .resume('run-id') with a specific run ID.",
            )

        storage = self._create_storage()
        result = run_in_event_loop(self._execute_resume(target_id, storage, validated))
        self._last_run_id = result.run_id
        return result

    async def _execute_run(
        self, engine: Engine, storage: Storage, items: list[dict], effective_config: dict,
        tags: dict[str, str] | None = None,
    ) -> Result:
        """Async run execution."""
        try:
            if await storage.run_exists(engine.run_id):
                raise DuplicateRunError(engine.run_id)

            config_dict = {k: v for k, v in effective_config.items() if k != "storage"}
            func_name = getattr(self._func, '__qualname__', '') or getattr(self._func, '__name__', '')
            await storage.create_run(engine.run_id, config_dict, self._func_hash, items, tags=tags, func_name=func_name)

            result = await engine.run()
            return result
        finally:
            await storage.close()

    async def _execute_resume(self, run_id: str, storage: Storage, overrides: dict) -> Result:
        """Async resume execution."""
        try:
            run_record = await storage.get_run(run_id)

            if run_record.func_hash != self._func_hash:
                logger.warning(
                    "Function hash changed since run %s was created.",
                    run_id,
                )

            # Use stored config as base, merge overrides
            stored_config = run_record.config
            effective_config = {**stored_config, **overrides}

            # Persist updated config
            if overrides:
                await storage.update_run_config(run_id, effective_config)

            failed_items = await storage.get_items_by_status(run_id, "failed")
            pending_items = await storage.get_items_by_status(run_id, "pending")
            to_retry = failed_items + pending_items

            if not to_retry:
                all_items = await storage.get_all_items(run_id)
                result_items = []
                for item_record in all_items:
                    output = None
                    if item_record.status == "completed":
                        output = await storage.load_item_output(run_id, item_record.index)
                    input_data = await storage.load_item_input(run_id, item_record.index)
                    result_items.append(ResultItem(
                        index=item_record.index,
                        input=input_data,
                        output=output,
                        status=item_record.status,
                        error=item_record.error,
                        attempts=item_record.attempts,
                        elapsed=item_record.elapsed,
                    ))
                return Result(items=result_items, run_id=run_id, elapsed=run_record.elapsed, tags=run_record.tags)

            items_to_run = []
            index_map = {}
            for i, item_record in enumerate(to_retry):
                input_data = await storage.load_item_input(run_id, item_record.index)
                items_to_run.append(input_data)
                index_map[i] = item_record.index

            engine_config = self._build_engine_config_from(effective_config, len(items_to_run))

            # Compute prior completed count for resume progress reporting
            all_items_pre = await storage.get_all_items(run_id)
            prior_completed = sum(1 for it in all_items_pre if it.status == "completed")

            engine = Engine(
                func=self._func,
                is_async=self._is_async,
                items=items_to_run,
                config=engine_config,
                storage=storage,
                run_id=run_id,
                index_map=index_map,
                resume_context={
                    "total_items": run_record.total_items,
                    "prior_completed": prior_completed,
                },
            )
            await engine.run()

            all_items = await storage.get_all_items(run_id)
            result_items = []
            for item_record in all_items:
                output = None
                if item_record.status == "completed":
                    output = await storage.load_item_output(run_id, item_record.index)
                input_data = await storage.load_item_input(run_id, item_record.index)
                result_items.append(ResultItem(
                    index=item_record.index,
                    input=input_data,
                    output=output,
                    status=item_record.status,
                    error=item_record.error,
                    attempts=item_record.attempts,
                    elapsed=item_record.elapsed,
                ))

            # Re-read run record to get updated elapsed (engine accumulates it)
            updated_run = await storage.get_run(run_id)
            return Result(items=result_items, run_id=run_id, elapsed=updated_run.elapsed, tags=updated_run.tags)
        finally:
            await storage.close()

    def _create_storage(self) -> Storage:
        storage_type = self._config.get("storage", "in_memory")
        if storage_type == "in_memory":
            if self._shared_storage is None:
                self._shared_storage = InMemoryStorage()
            return self._shared_storage
        from parawave.storage import create_storage
        return create_storage(storage_type)

    def _build_engine_config_from(self, config: dict, total_items: int) -> EngineConfig:
        """Build EngineConfig from a config dict (supports overrides)."""
        progress = self._resolve_progress_from(config, total_items)
        retry = config.get("retry")

        return EngineConfig(
            max_concurrency=config.get("max_concurrency", 10),
            rate_limit=config.get("rate_limit"),
            rate_period=config.get("rate_period", 1),
            retry_policy=retry,
            task_timeout=config.get("task_timeout", 60),
            run_timeout=config.get("run_timeout"),
            stop_on_consecutive_failures=config.get("stop_on_consecutive_failures"),
            progress=progress,
            on_start=config.get("on_start", []),
            on_retry=config.get("on_retry", []),
            on_item_complete=config.get("on_item_complete", []),
            on_item_error=config.get("on_item_error", []),
            on_complete=config.get("on_complete", []),
            warmup=config.get("warmup", False),
        )

    def _resolve_progress_from(self, config: dict, total_items: int):
        progress = config.get("progress", "console")
        if progress is None:
            return None
        if progress == "console":
            return ConsoleProgress()
        if progress == "bar":
            return create_bar_progress(total_items)
        if callable(progress):
            return progress
        return ConsoleProgress()

    def _build_engine_config(self, total_items: int) -> EngineConfig:
        return self._build_engine_config_from(self._config, total_items)

    def _resolve_progress(self, total_items: int):
        return self._resolve_progress_from(self._config, total_items)

    @staticmethod
    def _compute_func_hash(func: Callable) -> str:
        try:
            source = inspect.getsource(func)
            return hashlib.sha256(source.encode()).hexdigest()[:16]
        except (OSError, TypeError):
            return "unknown"
