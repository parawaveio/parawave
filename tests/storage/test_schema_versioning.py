"""Tests for SQLite schema versioning."""

import pytest
from pathlib import Path
from parawave.storage.sqlite.sqlite import SqliteStore


@pytest.fixture
async def store(tmp_path):
    s = SqliteStore(tmp_path / "parawave.db")
    await s.initialize()
    yield s
    await s.close()


class TestSchemaVersioning:
    async def test_fresh_db_has_meta_table(self, store):
        """Fresh database should have _meta table with schema_version."""
        async with store._db.execute(
            "SELECT value FROM _meta WHERE key = 'schema_version'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert int(row["value"]) >= 1

    async def test_fresh_db_has_parawave_version(self, store):
        """Fresh database should store the parawave package version."""
        async with store._db.execute(
            "SELECT value FROM _meta WHERE key = 'parawave_version'"
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert len(row["value"]) > 0

    async def test_schema_version_matches_current(self, store):
        """Schema version should match SCHEMA_VERSION constant."""
        from parawave.storage.sqlite.sqlite import SCHEMA_VERSION
        async with store._db.execute(
            "SELECT value FROM _meta WHERE key = 'schema_version'"
        ) as cursor:
            row = await cursor.fetchone()
        assert int(row["value"]) == SCHEMA_VERSION

    async def test_no_adhoc_migrations_remain(self, store):
        """The ad-hoc ALTER TABLE migrations should be removed."""
        import inspect
        from parawave.storage.sqlite.sqlite import SqliteStore
        source = inspect.getsource(SqliteStore.initialize)
        assert "ALTER TABLE" not in source
        assert "duplicate column name" not in source


class TestPreVersioningMigration:
    """Test that databases created before schema versioning get migrated correctly."""

    async def test_pre_versioning_db_gets_func_name_column(self, tmp_path):
        """A pre-versioning DB (no _meta, no func_name) should get migrated."""
        import aiosqlite

        db_path = tmp_path / "old.db"

        # Create a v1-style database: runs + items tables WITHOUT func_name
        async with aiosqlite.connect(db_path) as db:
            await db.executescript("""
                CREATE TABLE runs (
                    run_id TEXT PRIMARY KEY,
                    func_hash TEXT NOT NULL,
                    config TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    tags TEXT,
                    created_at TEXT,
                    elapsed REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE items (
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
            """)
            # Insert a row so it's not empty
            await db.execute(
                "INSERT INTO runs (run_id, func_hash, config, total_items) VALUES (?, ?, ?, ?)",
                ("old-run", "abc123", "{}", 5),
            )
            await db.commit()

        # Now open with current code — should detect pre-versioning and migrate
        store = SqliteStore(db_path)
        await store.initialize()

        try:
            # Verify func_name column was added via migration
            async with store._db.execute("PRAGMA table_info(runs)") as cursor:
                columns = [row["name"] for row in await cursor.fetchall()]
            assert "func_name" in columns, f"func_name missing from columns: {columns}"

            # Verify schema_version was set
            async with store._db.execute(
                "SELECT value FROM _meta WHERE key = 'schema_version'"
            ) as cursor:
                row = await cursor.fetchone()
            from parawave.storage.sqlite.sqlite import SCHEMA_VERSION
            assert int(row["value"]) == SCHEMA_VERSION

            # Verify old data is still accessible
            async with store._db.execute("SELECT func_name FROM runs WHERE run_id = 'old-run'") as cursor:
                row = await cursor.fetchone()
            assert row["func_name"] == ""  # default value from migration
        finally:
            await store.close()
