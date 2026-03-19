"""Storage backends for parawave."""

from __future__ import annotations

import os
import sys
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


def get_data_dir() -> Path:
    """Return the platform-specific default directory for parawave data.

    Follows platform conventions:
        macOS:   ~/Library/Application Support/parawave
        Linux:   ~/.local/share/parawave  (XDG Base Directory Specification)
        Windows: %LOCALAPPDATA%\\parawave

    Override with the PARAWAVE_DATA_DIR environment variable.
    """
    env_dir = os.environ.get("PARAWAVE_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    home = Path.home()

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "parawave"
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "parawave"
        return home / "AppData" / "Local" / "parawave"
    else:
        # Linux/Unix: XDG Base Directory Specification
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / "parawave"
        return home / ".local" / "share" / "parawave"


def _create_sqlite_storage(**kw):
    try:
        from parawave.storage.sqlite import SqliteStorage as _Sqlite
    except ImportError:
        raise ImportError(
            "SQLite storage requires two lightweight, pure-Python packages: aiosqlite, aiofiles. "
            "Install with: pip install parawave[sqlite]"
        ) from None
    return _Sqlite(Path(kw.get("path", str(get_data_dir()))))


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
