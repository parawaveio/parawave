"""Tests for SQLite storage resilience to corruption and permission errors."""

import os
import pytest
from parawave.storage.sqlite.sqlite import SqliteStore
from parawave.errors import StorageError


class TestSqliteResilience:
    async def test_corrupted_db_file(self, tmp_path):
        """Corrupted DB file should raise an error, not crash silently."""
        db_path = tmp_path / "parawave.db"
        db_path.write_bytes(b"this is not a valid sqlite database")
        store = SqliteStore(db_path)
        try:
            with pytest.raises(Exception):  # aiosqlite or sqlite3 error
                await store.initialize()
        finally:
            await store.close()

    async def test_permission_denied_on_db_path(self, tmp_path):
        """Read-only directory should raise clear error."""
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        os.chmod(read_only_dir, 0o444)
        store = SqliteStore(read_only_dir / "subdir" / "parawave.db")
        try:
            with pytest.raises((PermissionError, OSError, StorageError)):
                await store.initialize()
        finally:
            os.chmod(read_only_dir, 0o755)
            await store.close()

    async def test_fresh_db_created_on_new_path(self, tmp_path):
        """New path should create a fresh database without errors."""
        db_path = tmp_path / "new_dir" / "parawave.db"
        store = SqliteStore(db_path)
        await store.initialize()
        assert db_path.exists()
        await store.close()
