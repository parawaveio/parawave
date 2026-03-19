"""SQLite storage backend — SQLite for metadata, JSONL for data payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parawave.storage.sqlite.jsonl import JsonlStore
from parawave.storage.sqlite.sqlite import SqliteStore
from parawave.storage.models import ItemRecord, RunInfo, RunRecord, hash_input as _hash_input


class SqliteStorage:
    """Persistent storage combining SQLite (metadata) and JSONL (data).

    Directory layout:
        {base_dir}/parawave.db          — SQLite database
        {base_dir}/runs/{run_id}/       — JSONL files per run
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._sqlite = SqliteStore(base_dir / "parawave.db")
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self._sqlite.initialize()
            self._initialized = True

    def _jsonl(self, run_id: str) -> JsonlStore:
        return JsonlStore(self._base_dir / "runs" / run_id)

    async def create_run(
        self, run_id: str, config: dict, func_hash: str, items: list[dict],
        tags: dict[str, str] | None = None,
        func_name: str = "",
    ) -> None:
        await self._ensure_initialized()
        created_at = datetime.now(timezone.utc).isoformat()
        input_hashes = [_hash_input(item) for item in items]
        await self._sqlite.create_run(run_id, config, func_hash, len(items), tags=tags, created_at=created_at, func_name=func_name)
        await self._sqlite.create_items(run_id, len(items), input_hashes)
        await self._jsonl(run_id).write_inputs(items)

    async def get_run(self, run_id: str) -> RunRecord:
        await self._ensure_initialized()
        return await self._sqlite.get_run(run_id)

    async def run_exists(self, run_id: str) -> bool:
        await self._ensure_initialized()
        return await self._sqlite.run_exists(run_id)

    async def update_item_status(
        self, run_id: str, index: int, status: str, error: str | None,
        attempts: int = 1, elapsed: float = 0.0,
    ) -> None:
        await self._ensure_initialized()
        await self._sqlite.update_item_status(run_id, index, status, error, attempts, elapsed)

    async def get_items_by_status(
        self, run_id: str, status: str
    ) -> list[ItemRecord]:
        await self._ensure_initialized()
        return await self._sqlite.get_items_by_status(run_id, status)

    async def get_all_items(self, run_id: str) -> list[ItemRecord]:
        await self._ensure_initialized()
        return await self._sqlite.get_all_items(run_id)

    async def save_item_output(
        self, run_id: str, index: int, output: Any
    ) -> None:
        await self._jsonl(run_id).write_output(index, output)

    async def load_item_output(self, run_id: str, index: int) -> Any:
        return await self._jsonl(run_id).read_output(index)

    async def load_item_input(self, run_id: str, index: int) -> dict:
        return await self._jsonl(run_id).read_input(index)

    async def get_item_input_hash(self, run_id: str, index: int) -> str:
        await self._ensure_initialized()
        return await self._sqlite.get_item_input_hash(run_id, index)

    async def update_run_config(self, run_id: str, config: dict) -> None:
        await self._ensure_initialized()
        await self._sqlite.update_run_config(run_id, config)

    async def update_run_status(self, run_id: str, status: str) -> None:
        await self._ensure_initialized()
        await self._sqlite.update_run_status(run_id, status)

    async def update_run_elapsed(self, run_id: str, elapsed: float) -> None:
        await self._ensure_initialized()
        await self._sqlite.update_run_elapsed(run_id, elapsed)

    async def get_run_elapsed(self, run_id: str) -> float:
        await self._ensure_initialized()
        return await self._sqlite.get_run_elapsed(run_id)

    async def update_tags(self, run_id: str, tags: dict[str, str]) -> None:
        await self._ensure_initialized()
        await self._sqlite.update_tags(run_id, tags)

    async def get_run_info(self, run_id: str) -> RunInfo:
        await self._ensure_initialized()
        return await self._sqlite.get_run_info(run_id)

    async def list_runs(
        self,
        tags: dict[str, str] | None = None,
        status: str | None = None,
    ) -> list[RunInfo]:
        await self._ensure_initialized()
        return await self._sqlite.list_runs(tags=tags, status=status)

    async def delete_run(self, run_id: str) -> None:
        await self._ensure_initialized()
        await self._sqlite.delete_run(run_id)
        run_dir = self._base_dir / "runs" / run_id
        if run_dir.exists():
            import shutil
            shutil.rmtree(run_dir)

    async def load_result(self, run_id: str) -> "Result":
        from parawave.result import Result, ResultItem
        await self._ensure_initialized()
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
        await self._sqlite.close()
