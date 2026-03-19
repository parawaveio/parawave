"""Engine — core orchestration: queue, workers, rate limiting, progress."""

from __future__ import annotations

import asyncio
import sys
from parawave.log import get_logger
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from parawave.hooks import fire_hooks
from parawave.progress.base import ProgressCallback, ProgressSnapshot
from parawave.result import Result, ResultItem
from parawave.retry import RetryPolicy
from parawave.runner import run_item
from parawave.shutdown import ShutdownHandler
from parawave.storage.base import Storage

logger = get_logger(__name__)


@dataclass
class EngineConfig:
    """Configuration passed from Process to Engine."""

    max_concurrency: int = 10
    rate_limit: int | None = None
    rate_period: float = 1
    retry_policy: RetryPolicy | None = None
    task_timeout: float = 60
    run_timeout: float | None = None
    stop_on_consecutive_failures: int | None = None
    progress: ProgressCallback | None = None
    on_start: list[Callable] = field(default_factory=list)
    on_retry: list[Callable] = field(default_factory=list)
    on_item_complete: list[Callable] = field(default_factory=list)
    on_item_error: list[Callable] = field(default_factory=list)
    on_complete: list[Callable] = field(default_factory=list)
    warmup: bool = False


class Engine:
    """Orchestrates parallel execution of items."""

    def __init__(
        self,
        func: Callable,
        is_async: bool,
        items: list[dict],
        config: EngineConfig,
        storage: Storage,
        run_id: str | None = None,
        index_map: dict[int, int] | None = None,
        tags: dict[str, str] | None = None,
        resume_context: dict | None = None,
    ) -> None:
        self._func = func
        self._is_async = is_async
        self._items = items
        self._config = config
        self._storage = storage
        self._run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        self._index_map = index_map  # maps local index -> storage index (for resume)
        self._tags = tags

        # Resume context: total_items and prior_completed from the original run
        self._resume_context = resume_context

        # State
        self._results: dict[int, ResultItem] = {}
        self._consecutive_failures = 0
        self._completed_count = 0
        self._failed_count = 0
        self._retry_count = 0
        self._running = 0
        self._stop_flag = False
        self._shutdown = ShutdownHandler()

        # Rate limiter state (token bucket)
        self._tokens: float = 0
        self._last_refill: float = 0
        self._token_lock: asyncio.Lock | None = None  # lazy-init for Python 3.9 compat

    @property
    def run_id(self) -> str:
        return self._run_id

    async def _persist_item(self, item: ResultItem) -> None:
        """Persist a single item's result to storage immediately."""
        storage_index = self._index_map[item.index] if self._index_map else item.index
        try:
            await self._storage.update_item_status(
                self._run_id, storage_index, item.status, item.error, item.attempts, item.elapsed
            )
            if item.ok:
                await self._storage.save_item_output(
                    self._run_id, storage_index, item.output
                )
        except Exception:
            logger.error(
                "Failed to persist item %d to storage — result may be lost on crash",
                storage_index,
                exc_info=True,
            )

    async def run(self) -> Result:
        """Execute all items and return a Result."""
        start_time = time.monotonic()

        # Print run start
        if self._resume_context:
            prior = self._resume_context["prior_completed"]
            total = self._resume_context["total_items"]
            print(
                f"[parawave] Resuming {self._run_id} | {prior}/{total} previously completed | concurrency={self._config.max_concurrency}",
                file=sys.stderr, flush=True,
            )
        else:
            print(
                f"[parawave] Starting {self._run_id} | {len(self._items)} items | concurrency={self._config.max_concurrency}",
                file=sys.stderr, flush=True,
            )

        # Fire on_start hooks
        fire_hooks(self._config.on_start, self._run_id, len(self._items))

        # Create queue of (index, input_data)
        queue: asyncio.Queue[tuple[int, dict]] = asyncio.Queue()
        if self._config.warmup and self._items:
            queue.put_nowait((0, self._items[0]))
        else:
            for i, item in enumerate(self._items):
                queue.put_nowait((i, item))

        # Initialize rate limiter
        if self._config.rate_limit:
            self._tokens = float(self._config.rate_limit)
            self._last_refill = time.monotonic()

        # Install shutdown handler
        try:
            self._shutdown.install()
        except ValueError:
            # Can't install signal handler from non-main thread (e.g., in tests)
            pass

        try:
            if self._config.warmup and self._items:
                print(
                    "[parawave] Warmup: testing first item before scaling up",
                    file=sys.stderr, flush=True,
                )
                # Warmup: 1 worker processes first item, exits on QueueEmpty
                warmup_worker = asyncio.create_task(self._worker(queue, start_time))
                await warmup_worker

                # If warmup succeeded, populate remaining items and scale up
                if self._failed_count == 0 and not self._stop_flag:
                    print(
                        f"[parawave] Warmup: passed, scaling to concurrency={self._config.max_concurrency}",
                        file=sys.stderr, flush=True,
                    )
                    for i in range(1, len(self._items)):
                        queue.put_nowait((i, self._items[i]))
                    num_workers = min(self._config.max_concurrency, queue.qsize()) if not queue.empty() else 0
                    workers = [
                        asyncio.create_task(self._worker(queue, start_time))
                        for _ in range(num_workers)
                    ]
                else:
                    # Warmup failed — mark remaining items as pending
                    print(
                        "[parawave] Stopped: warmup failed",
                        file=sys.stderr, flush=True,
                    )
                    self._stop_flag = True
                    for i in range(1, len(self._items)):
                        self._results[i] = ResultItem(
                            index=i, input=self._items[i], output=None,
                            status="pending", error=None,
                        )
                    workers = []
            else:
                # No warmup — launch all workers immediately (existing behavior)
                num_workers = min(self._config.max_concurrency, len(self._items)) if self._items else 0
                workers = [
                    asyncio.create_task(self._worker(queue, start_time))
                    for _ in range(num_workers)
                ]

            # Wrap queue.join() in a task so it can be cancelled by timeout watcher
            join_task = asyncio.create_task(queue.join())

            # Launch timeout watcher if configured
            timeout_task = None
            if self._config.run_timeout:
                timeout_task = asyncio.create_task(
                    self._run_timeout_watcher(workers, join_task)
                )

            # Wait for queue to drain (or be cancelled by timeout)
            try:
                await join_task
            except asyncio.CancelledError:
                pass

            # Cancel timeout watcher and workers
            if timeout_task:
                timeout_task.cancel()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            try:
                self._shutdown.uninstall()
            except ValueError:
                pass

        # Build final result
        elapsed = time.monotonic() - start_time

        # Accumulate elapsed with previously stored value
        total_elapsed = elapsed
        try:
            stored_elapsed = await self._storage.get_run_elapsed(self._run_id)
            total_elapsed = stored_elapsed + elapsed
            await self._storage.update_run_elapsed(self._run_id, total_elapsed)
            # Mark run as completed
            await self._storage.update_run_status(self._run_id, "completed")
        except Exception:
            logger.debug(
                "Could not update run elapsed/status for %s",
                self._run_id,
                exc_info=True,
            )

        result = self._build_result(total_elapsed)

        # Print stop reason if early stop triggered
        if self._stop_flag and self._config.stop_on_consecutive_failures:
            n = self._config.stop_on_consecutive_failures
            print(
                f"[parawave] Stopped: {n} consecutive failures",
                file=sys.stderr, flush=True,
            )

        # Print run finish — on resume, show full run total not just retry subset
        if self._resume_context:
            total = self._resume_context["total_items"]
            prior = self._resume_context["prior_completed"]
            completed = prior + self._completed_count
            failed = self._failed_count
            pending = total - completed - failed
            parts = [f"{completed}/{total} completed"]
            if failed > 0:
                parts.append(f"{failed} failed")
            if pending > 0:
                parts.append(f"{pending} pending")
            if total_elapsed > 0:
                parts.append(f"{total_elapsed:.1f}s")
                ips = completed / total_elapsed if total_elapsed > 0 else 0
                parts.append(f"{ips:.1f} items/s")
            print(
                f"[parawave] Completed {self._run_id} | {' | '.join(parts)}",
                file=sys.stderr, flush=True,
            )
        else:
            print(
                f"[parawave] Completed {self._run_id} | {result.summary}",
                file=sys.stderr, flush=True,
            )

        # Fire on_complete hooks
        fire_hooks(self._config.on_complete, result)

        return result

    async def _worker(
        self, queue: asyncio.Queue, start_time: float
    ) -> None:
        """Worker loop: pull items from queue and process them."""
        while True:
            try:
                index, input_data = queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            # Check stop conditions
            if self._stop_flag or self._shutdown.force_stop or self._shutdown.should_stop:
                # Mark remaining as pending
                self._results[index] = ResultItem(
                    index=index,
                    input=input_data,
                    output=None,
                    status="pending",
                    error=None,
                )
                queue.task_done()
                continue

            # Rate limiting
            if self._config.rate_limit:
                await self._acquire_token()

            # Build rate limit callback for retries (spec: retries consume tokens)
            _acquire_rate_token = self._acquire_token if self._config.rate_limit else None

            # Execute item
            self._running += 1
            item = await run_item(
                func=self._func,
                index=index,
                input_data=input_data,
                is_async=self._is_async,
                retry_policy=self._config.retry_policy,
                task_timeout=self._config.task_timeout,
                _acquire_rate_token=_acquire_rate_token,
                on_retry_hooks=self._config.on_retry,
            )

            self._running -= 1
            self._retry_count += item.attempts - 1  # attempts includes initial try
            self._results[index] = item

            # Persist to storage immediately
            await self._persist_item(item)

            # Fire per-item hooks and update counters
            if item.ok:
                self._completed_count += 1
                self._consecutive_failures = 0
                fire_hooks(self._config.on_item_complete, item)
            else:
                self._failed_count += 1
                self._consecutive_failures += 1
                fire_hooks(self._config.on_item_error, item)

            # Check consecutive failures
            if (
                self._config.stop_on_consecutive_failures
                and self._consecutive_failures >= self._config.stop_on_consecutive_failures
            ):
                logger.warning(
                    "Stopping: %d consecutive failures",
                    self._consecutive_failures,
                )
                self._stop_flag = True

            # Progress update — count against full run total on resume
            if self._config.progress:
                elapsed = time.monotonic() - start_time
                if self._resume_context:
                    total = self._resume_context["total_items"]
                    prior = self._resume_context["prior_completed"]
                    snapshot = ProgressSnapshot(
                        total=total,
                        completed=prior + self._completed_count,
                        failed=self._failed_count,
                        pending=total - prior - len(self._results),
                        running=self._running,
                        elapsed=elapsed,
                        retries=self._retry_count,
                    )
                else:
                    snapshot = ProgressSnapshot(
                        total=len(self._items),
                        completed=self._completed_count,
                        failed=self._failed_count,
                        pending=len(self._items) - len(self._results),
                        running=self._running,
                        elapsed=elapsed,
                        retries=self._retry_count,
                    )
                self._config.progress.on_update(snapshot)

            queue.task_done()

    async def _run_timeout_watcher(
        self, workers: list[asyncio.Task], join_task: asyncio.Task
    ) -> None:
        """Cancel all workers when run_timeout is reached."""
        await asyncio.sleep(self._config.run_timeout)
        self._stop_flag = True
        self._shutdown.force_shutdown()
        for w in workers:
            w.cancel()
        join_task.cancel()
        print(
            f"[parawave] Run timeout ({self._config.run_timeout}s) reached. Cancelling all tasks.",
            file=sys.stderr, flush=True,
        )

    async def _acquire_token(self) -> None:
        """Token bucket rate limiter. Safe for cancellation."""
        if self._token_lock is None:
            self._token_lock = asyncio.Lock()
        await self._token_lock.acquire()
        try:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens += elapsed * (self._config.rate_limit / self._config.rate_period)
                self._tokens = min(self._tokens, float(self._config.rate_limit))
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                # Calculate wait time for next token
                wait_time = (1.0 - self._tokens) / (self._config.rate_limit / self._config.rate_period)
                self._token_lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._token_lock.acquire()
        finally:
            self._token_lock.release()

    def _build_result(self, elapsed: float = 0.0) -> Result:
        """Build the final Result from collected items."""
        items = []
        for i in range(len(self._items)):
            if i in self._results:
                items.append(self._results[i])
            else:
                items.append(
                    ResultItem(
                        index=i,
                        input=self._items[i],
                        output=None,
                        status="pending",
                        error=None,
                    )
                )

        return Result(items=items, run_id=self._run_id, elapsed=elapsed, tags=self._tags)
