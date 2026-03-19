"""Storage backends for parawave."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from parawave.storage.base import Storage
from parawave.storage.memory import InMemoryStorage
from parawave.storage.models import RunRecord, ItemRecord, RunInfo

# Lazy import — SqliteStorage requires aiosqlite + aiofiles
try:
    from parawave.storage.sqlite import SqliteStorage
except ImportError:
    SqliteStorage = None  # type: ignore


def _create_sqlite_storage(**kw):
    try:
        from parawave.storage.sqlite import SqliteStorage as _Sqlite
    except ImportError:
        raise ImportError(
            "SQLite storage requires two lightweight, pure-Python packages: aiosqlite, aiofiles. "
            "Install with: pip install parawave[sqlite]"
        ) from None
    return _Sqlite(Path(kw.get("path", ".parawave")))


_REGISTRY: dict[str, Callable] = {
    "sqlite": _create_sqlite_storage,
    "in_memory": lambda **kw: InMemoryStorage(),
}


def register_storage(name: str, factory: Callable) -> None:
    """Register a custom storage backend."""
    _REGISTRY[name] = factory


def create_storage(name: str, **kwargs):
    """Create a storage instance by name."""
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown storage: {name!r}. Available: {available}")
    return _REGISTRY[name](**kwargs)


__all__ = [
    "Storage", "InMemoryStorage", "RunRecord", "ItemRecord",
    "RunInfo", "register_storage", "create_storage",
]
if SqliteStorage is not None:
    __all__.append("SqliteStorage")
