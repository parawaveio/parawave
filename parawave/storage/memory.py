"""In-memory storage backend — for testing and dry_run."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from parawave.errors import RunNotFoundError
from parawave.storage.models import ItemRecord, RunInfo, RunRecord, hash_input, validate_tag_keys


class InMemoryStorage:
    """Non-persistent storage backend. All data lives in memory."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._items: dict[str, list[ItemRecord]] = {}
        self._inputs: dict[str, list[dict]] = {}
        self._outputs: dict[tuple[str, int], Any] = {}
        self._input_hashes: dict[str, list[str]] = {}

    async def create_run(
        self, run_id: str, config: dict, func_hash: str, items: list[dict],
        tags: dict[str, str] | None = None,
        func_name: str = "",
    ) -> None:
        validate_tag_keys(tags)
        created_at = datetime.now(timezone.utc).isoformat()
        self._runs[run_id] = RunRecord(
            run_id=run_id,
            func_hash=func_hash,
            config=config,
            total_items=len(items),
            func_name=func_name,
            tags=tags,
            created_at=created_at,
            status="running",
        )
        self._inputs[run_id] = list(items)
        self._input_hashes[run_id] = [hash_input(item) for item in items]
        self._items[run_id] = [
            ItemRecord(
                run_id=run_id,
                index=i,
                status="pending",
                input_hash=self._input_hashes[run_id][i],
                error=None,
            )
            for i in range(len(items))
        ]

    async def get_run(self, run_id: str) -> RunRecord:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        return self._runs[run_id]

    async def run_exists(self, run_id: str) -> bool:
        return run_id in self._runs

    async def update_item_status(
        self, run_id: str, index: int, status: str, error: str | None,
        attempts: int = 1, elapsed: float = 0.0,
    ) -> None:
        self._items[run_id][index].status = status
        self._items[run_id][index].error = error
        self._items[run_id][index].attempts = attempts
        self._items[run_id][index].elapsed = elapsed

    async def get_items_by_status(
        self, run_id: str, status: str
    ) -> list[ItemRecord]:
        return [item for item in self._items[run_id] if item.status == status]

    async def get_all_items(self, run_id: str) -> list[ItemRecord]:
        return list(self._items[run_id])

    async def save_item_output(
        self, run_id: str, index: int, output: Any
    ) -> None:
        self._outputs[(run_id, index)] = output

    async def load_item_output(self, run_id: str, index: int) -> Any:
        return self._outputs.get((run_id, index))

    async def load_item_input(self, run_id: str, index: int) -> dict:
        return self._inputs[run_id][index]

    async def get_item_input_hash(self, run_id: str, index: int) -> str:
        return self._input_hashes[run_id][index]

    async def update_run_config(self, run_id: str, config: dict) -> None:
        existing = self._runs[run_id]
        self._runs[run_id] = RunRecord(
            run_id=existing.run_id, func_hash=existing.func_hash,
            config=config, total_items=existing.total_items,
            func_name=existing.func_name,
            tags=existing.tags, created_at=existing.created_at,
            elapsed=existing.elapsed, status=existing.status,
        )

    async def update_run_status(self, run_id: str, status: str) -> None:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        self._runs[run_id].status = status

    async def update_run_elapsed(self, run_id: str, elapsed: float) -> None:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        self._runs[run_id].elapsed = elapsed

    async def get_run_elapsed(self, run_id: str) -> float:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        return self._runs[run_id].elapsed

    async def update_tags(self, run_id: str, tags: dict[str, str]) -> None:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        validate_tag_keys(tags)
        self._runs[run_id].tags = tags

    async def delete_run(self, run_id: str) -> None:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        self._runs.pop(run_id, None)
        self._items.pop(run_id, None)
        self._inputs.pop(run_id, None)
        self._input_hashes.pop(run_id, None)
        # Remove outputs for this run
        keys_to_delete = [k for k in self._outputs if k[0] == run_id]
        for k in keys_to_delete:
            del self._outputs[k]

    async def get_run_info(self, run_id: str) -> RunInfo:
        if run_id not in self._runs:
            raise RunNotFoundError(run_id)
        run = self._runs[run_id]
        items = self._items.get(run_id, [])
        num_completed = sum(1 for i in items if i.status == "completed")
        num_failed = sum(1 for i in items if i.status == "failed")
        num_pending = sum(1 for i in items if i.status == "pending")
        num_retried = sum(1 for i in items if i.attempts > 1)
        num_attempts = sum(i.attempts for i in items)
        created_at_dt = (
            datetime.fromisoformat(run.created_at).astimezone()
            if run.created_at
            else datetime.now(timezone.utc).astimezone()
        )
        return RunInfo(
            run_id=run.run_id,
            func_hash=run.func_hash,
            status=run.status,
            total_items=run.total_items,
            num_completed=num_completed,
            num_failed=num_failed,
            num_pending=num_pending,
            num_retried=num_retried,
            num_attempts=num_attempts,
            func_name=run.func_name,
            tags=run.tags,
            created_at=created_at_dt,
            elapsed=run.elapsed,
        )

    async def list_runs(
        self,
        tags: dict[str, str] | None = None,
        status: str | None = None,
    ) -> list[RunInfo]:
        results = []
        for run_id, run in self._runs.items():
            if status is not None and run.status != status:
                continue
            if tags is not None:
                if run.tags is None:
                    continue
                if not all(run.tags.get(k) == v for k, v in tags.items()):
                    continue
            info = await self.get_run_info(run_id)
            results.append(info)
        # Sort by created_at descending
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    async def load_result(self, run_id: str) -> "Result":
        from parawave.result import Result, ResultItem
        run = await self.get_run(run_id)
        all_items = await self.get_all_items(run_id)
        result_items = []
        for item_record in all_items:
            input_data = await self.load_item_input(run_id, item_record.index)
            output = None
            if item_record.status == "completed":
                output = await self.load_item_output(run_id, item_record.index)
            result_items.append(ResultItem(
                index=item_record.index, input=input_data, output=output,
                status=item_record.status, error=item_record.error,
                attempts=item_record.attempts, elapsed=item_record.elapsed,
            ))
        return Result(items=result_items, run_id=run_id, elapsed=run.elapsed, tags=run.tags)

    async def close(self) -> None:
        pass
