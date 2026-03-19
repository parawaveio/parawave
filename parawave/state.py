"""SharedState — thread-safe shared state utility."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator


class SharedState:
    """Thread-safe dictionary for sharing state between parallel tasks.

    Accessed by user functions via normal Python scoping (closure).
    Not wired into parawave internals.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial) if initial else {}
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value."""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a value."""
        with self._lock:
            self._data[key] = value

    def increment(self, key: str, amount: int | float = 1) -> None:
        """Atomic increment."""
        with self._lock:
            self._data[key] = self._data.get(key, 0) + amount

    def append(self, key: str, value: Any) -> None:
        """Atomic list append."""
        with self._lock:
            if key not in self._data:
                self._data[key] = []
            self._data[key].append(value)

    def update(self, d: dict[str, Any]) -> None:
        """Atomic multi-set."""
        with self._lock:
            self._data.update(d)

    def to_dict(self) -> dict[str, Any]:
        """Snapshot as plain dict (copy)."""
        with self._lock:
            return dict(self._data)

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Context manager for compound operations."""
        with self._lock:
            yield
