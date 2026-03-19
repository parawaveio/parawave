"""SQLite metadata store for run records and item statuses."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from parawave.log import get_logger
from parawave.errors import RunNotFoundError, StorageError
from parawave.storage.models import ItemRecord, RunInfo, RunRecord, validate_tag_keys


def _validate_tag_keys(tags: dict[str, str] | None) -> None:
    """Validate all tag keys are safe for SQL interpolation."""
    validate_tag_keys(tags)


def _parse_created_at(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc).astimezone()
    dt = datetime.fromisoformat(value)
    return dt.astimezone()  # convert to local timezone


class _ConfigEncoder(json.JSONEncoder):
    """JSON encoder that handles config objects like RetryPolicy and callables."""

    def default(self, o):
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            d = dataclasses.asdict(o)
            # Exception types in retryable/non_retryable -> store as names
            for key in ("retryable", "non_retryable"):
                if key in d and d[key] is not None:
                    d[key] = [t.__name__ if isinstance(t, type) else str(t) for t in getattr(o, key)]
            return d
        if callable(o):
            return f"<{getattr(o, '__name__', type(o).__name__)}>"
        return super().default(o)

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    func_hash TEXT NOT NULL,
    func_name TEXT NOT NULL DEFAULT '',
    config TEXT NOT NULL,
    total_items INTEGER NOT NULL,
    tags TEXT,
    created_at TEXT,
    elapsed REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS items (
    run_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_hash TEXT NOT NULL,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    elapsed REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (run_id, item_index),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""

SCHEMA_VERSION = 2

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS _meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_MIGRATIONS: dict[int, list[str]] = {
    # Version 1 is the baseline — CREATE TABLE handles it.
    2: ["ALTER TABLE runs ADD COLUMN func_name TEXT NOT NULL DEFAULT ''"],
}


def _get_parawave_version() -> str:
    try:
        from importlib.metadata import version
        return version("parawave")
    except Exception:
        return "0.1.0"


_RUN_INFO_QUERY = """
SELECT
    r.run_id, r.func_hash, r.func_name, r.status, r.total_items,
    r.tags, r.created_at, r.elapsed,
    COALESCE(SUM(CASE WHEN i.status='completed' THEN 1 ELSE 0 END), 0) as num_completed,
    COALESCE(SUM(CASE WHEN i.status='failed' THEN 1 ELSE 0 END), 0) as num_failed,
    COALESCE(SUM(CASE WHEN i.status='pending' THEN 1 ELSE 0 END), 0) as num_pending,
    COALESCE(SUM(CASE WHEN i.attempts > 1 THEN 1 ELSE 0 END), 0) as num_retried,
    COALESCE(SUM(i.attempts), 0) as num_attempts
FROM runs r
LEFT JOIN items i ON r.run_id = i.run_id
"""


class SqliteStore:
    """Async SQLite store for run metadata and item statuses."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._write_lock: asyncio.Lock | None = None  # lazy-init for Python 3.9 compat

    async def initialize(self) -> None:
        """Create tables if they don't exist, run migrations."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = asyncio.Lock()
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        # Performance PRAGMAs
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA cache_size=-2000")
        await self._db.execute("PRAGMA busy_timeout=60000")
        await self._db.executescript(_SCHEMA)
        await self._db.executescript(_META_SCHEMA)
        await self._db.commit()
        await self._run_migrations()

    async def _get_schema_version(self) -> int:
        async with self._db.execute(
            "SELECT value FROM _meta WHERE key = 'schema_version'"
        ) as cursor:
            row = await cursor.fetchone()
        return int(row["value"]) if row else 0

    async def _set_meta(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    async def _has_column(self, table: str, column: str) -> bool:
        """Check if a column exists in a table via PRAGMA."""
        async with self._db.execute(f"PRAGMA table_info({table})") as cursor:
            rows = await cursor.fetchall()
        return any(row["name"] == column for row in rows)

    async def _run_migrations(self) -> None:
        current = await self._get_schema_version()
        if current == 0:
            # Distinguish fresh DB (CREATE TABLE includes all columns)
            # from pre-versioning DB (may be missing columns like func_name)
            if await self._has_column("runs", "func_name"):
                # Fresh database — schema already at latest from CREATE TABLE
                await self._set_meta("schema_version", str(SCHEMA_VERSION))
                await self._set_meta("parawave_version", _get_parawave_version())
                await self._db.commit()
                return
            # Pre-versioning database — run all migrations from v1
            current = 1
        # Existing database — apply pending migrations
        for version in range(current + 1, SCHEMA_VERSION + 1):
            if version not in _MIGRATIONS:
                continue  # No migration needed for this version
            for sql in _MIGRATIONS[version]:
                await self._db.execute(sql)
            await self._set_meta("schema_version", str(version))
        await self._set_meta("parawave_version", _get_parawave_version())
        await self._db.commit()

    async def _execute_write(self, sql: str, params: tuple = ()) -> None:
        """Execute a write with single-writer lock and retry on database lock."""
        max_retries = 5
        base_delay = 0.1

        async with self._write_lock:
            if self._db is None:
                raise StorageError("SqliteStore not initialized. Call initialize() first.")
            for attempt in range(max_retries):
                try:
                    await self._db.execute(sql, params)
                    await self._db.commit()
                    return
                except Exception as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(-0.05, 0.05)
                        logger.warning(
                            "Database locked, retrying in %.2fs (%d/%d)",
                            delay, attempt + 1, max_retries,
                        )
                        await asyncio.sleep(delay)
                    else:
                        raise

    async def create_run(
        self, run_id: str, config: dict, func_hash: str, total_items: int,
        tags: dict[str, str] | None = None,
        created_at: str = "",
        func_name: str = "",
    ) -> None:
        _validate_tag_keys(tags)
        tags_json = json.dumps(tags) if tags is not None else None
        await self._execute_write(
            "INSERT INTO runs (run_id, func_hash, func_name, config, total_items, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, func_hash, func_name, json.dumps(config, cls=_ConfigEncoder), total_items, tags_json, created_at),
        )

    async def get_run(self, run_id: str) -> RunRecord:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        tags_raw = row["tags"]
        return RunRecord(
            run_id=row["run_id"],
            func_hash=row["func_hash"],
            config=json.loads(row["config"]),
            total_items=row["total_items"],
            func_name=row["func_name"],
            tags=json.loads(tags_raw) if tags_raw else None,
            created_at=row["created_at"] or "",
            elapsed=row["elapsed"],
            status=row["status"],
        )

    async def run_exists(self, run_id: str) -> bool:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def create_items(
        self, run_id: str, count: int, input_hashes: list[str]
    ) -> None:
        """Bulk-insert item records for a run."""
        rows = [
            (run_id, i, "pending", input_hashes[i], None)
            for i in range(count)
        ]
        max_retries = 5
        base_delay = 0.1
        async with self._write_lock:
            if self._db is None:
                raise StorageError("SqliteStore not initialized. Call initialize() first.")
            for attempt in range(max_retries):
                try:
                    await self._db.executemany(
                        "INSERT INTO items (run_id, item_index, status, input_hash, error) VALUES (?, ?, ?, ?, ?)",
                        rows,
                    )
                    await self._db.commit()
                    return
                except Exception as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(-0.05, 0.05)
                        logger.warning("Database locked, retrying in %.2fs (%d/%d)", delay, attempt + 1, max_retries)
                        await asyncio.sleep(delay)
                    else:
                        raise

    async def update_item_status(
        self, run_id: str, index: int, status: str, error: str | None,
        attempts: int = 1, elapsed: float = 0.0,
    ) -> None:
        await self._execute_write(
            "UPDATE items SET status = ?, error = ?, attempts = ?, elapsed = ? WHERE run_id = ? AND item_index = ?",
            (status, error, attempts, elapsed, run_id, index),
        )

    async def get_all_items(self, run_id: str) -> list[ItemRecord]:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT * FROM items WHERE run_id = ? ORDER BY item_index", (run_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            ItemRecord(
                run_id=row["run_id"],
                index=row["item_index"],
                status=row["status"],
                input_hash=row["input_hash"],
                error=row["error"],
                attempts=row["attempts"],
                elapsed=row["elapsed"],
            )
            for row in rows
        ]

    async def get_items_by_status(
        self, run_id: str, status: str
    ) -> list[ItemRecord]:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT * FROM items WHERE run_id = ? AND status = ? ORDER BY item_index",
            (run_id, status),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            ItemRecord(
                run_id=row["run_id"],
                index=row["item_index"],
                status=row["status"],
                input_hash=row["input_hash"],
                error=row["error"],
                attempts=row["attempts"],
                elapsed=row["elapsed"],
            )
            for row in rows
        ]

    async def get_item_input_hash(self, run_id: str, index: int) -> str:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT input_hash FROM items WHERE run_id = ? AND item_index = ?",
            (run_id, index),
        ) as cursor:
            row = await cursor.fetchone()
        return row["input_hash"]

    async def update_run_config(self, run_id: str, config: dict) -> None:
        await self._execute_write(
            "UPDATE runs SET config = ? WHERE run_id = ?",
            (json.dumps(config, cls=_ConfigEncoder), run_id),
        )

    async def update_run_status(self, run_id: str, status: str) -> None:
        await self._execute_write(
            "UPDATE runs SET status = ? WHERE run_id = ?",
            (status, run_id),
        )

    async def update_run_elapsed(self, run_id: str, elapsed: float) -> None:
        await self._execute_write(
            "UPDATE runs SET elapsed = ? WHERE run_id = ?",
            (elapsed, run_id),
        )

    async def get_run_elapsed(self, run_id: str) -> float:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        async with self._db.execute(
            "SELECT elapsed FROM runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row["elapsed"] if row else 0.0

    async def update_tags(self, run_id: str, tags: dict[str, str]) -> None:
        if not await self.run_exists(run_id):
            raise RunNotFoundError(run_id)
        _validate_tag_keys(tags)
        tags_json = json.dumps(tags) if tags is not None else None
        await self._execute_write(
            "UPDATE runs SET tags = ? WHERE run_id = ?",
            (tags_json, run_id),
        )

    async def delete_run(self, run_id: str) -> None:
        if not await self.run_exists(run_id):
            raise RunNotFoundError(run_id)
        async with self._write_lock:
            if self._db is None:
                raise StorageError("SqliteStore not initialized.")
            await self._db.execute("DELETE FROM items WHERE run_id = ?", (run_id,))
            await self._db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
            await self._db.commit()

    async def get_run_info(self, run_id: str) -> RunInfo:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        query = _RUN_INFO_QUERY + " WHERE r.run_id = ? GROUP BY r.run_id"
        async with self._db.execute(query, (run_id,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        tags_raw = row["tags"]
        return RunInfo(
            run_id=row["run_id"],
            func_hash=row["func_hash"],
            status=row["status"],
            total_items=row["total_items"],
            num_completed=row["num_completed"],
            num_failed=row["num_failed"],
            num_pending=row["num_pending"],
            num_retried=row["num_retried"],
            num_attempts=row["num_attempts"],
            func_name=row["func_name"],
            tags=json.loads(tags_raw) if tags_raw else None,
            created_at=_parse_created_at(row["created_at"] or ""),
            elapsed=row["elapsed"],
        )

    async def list_runs(
        self,
        tags: dict[str, str] | None = None,
        status: str | None = None,
    ) -> list[RunInfo]:
        if self._db is None:
            raise StorageError("SqliteStore not initialized. Call initialize() first.")
        conditions: list[str] = []
        params: list[str | float] = []
        if tags:
            _validate_tag_keys(tags)
            for key, value in tags.items():
                conditions.append(f"json_extract(r.tags, '$.{key}') = ?")
                params.append(value)
        if status:
            conditions.append("r.status = ?")
            params.append(status)
        where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        query = _RUN_INFO_QUERY + where_clause + " GROUP BY r.run_id ORDER BY r.created_at DESC"
        async with self._db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
        results: list[RunInfo] = []
        for row in rows:
            tags_raw = row["tags"]
            results.append(RunInfo(
                run_id=row["run_id"],
                func_hash=row["func_hash"],
                status=row["status"],
                total_items=row["total_items"],
                num_completed=row["num_completed"],
                num_failed=row["num_failed"],
                num_pending=row["num_pending"],
                num_retried=row["num_retried"],
                num_attempts=row["num_attempts"],
                func_name=row["func_name"],
                tags=json.loads(tags_raw) if tags_raw else None,
                created_at=_parse_created_at(row["created_at"] or ""),
                elapsed=row["elapsed"],
            ))
        return results

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
