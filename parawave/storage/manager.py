"""RunManager — data management interface for parawave runs."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from parawave._event_loop import run_in_event_loop
from parawave.result import Result
from parawave.storage.base import Storage
from parawave.storage.models import RunInfo

T = TypeVar("T")

_MISSING = object()


class RunManager:
    """Data management interface for parawave runs.

    Reads from and manages stored run data. Does not execute functions.
    When initialized with a string name, each method creates a fresh
    storage connection. When initialized with a Storage instance,
    the caller owns the lifecycle.
    """

    def __init__(self, storage: str | Storage = _MISSING, **kwargs: Any) -> None:
        if storage is _MISSING:
            from parawave.storage import _REGISTRY
            available = ", ".join(_REGISTRY.keys())
            raise TypeError(
                f"RunManager requires a storage backend. "
                f"Available: {available}. "
                f"Example: RunManager('sqlite')"
            )
        if isinstance(storage, str):
            self._storage_name = storage
            self._storage_kwargs = kwargs
            self._user_storage: Storage | None = None
        else:
            self._user_storage = storage

    def _query(self, operation: Callable[..., Any]) -> Any:
        if self._user_storage is not None:
            async def _run():
                return await operation(self._user_storage)
            return run_in_event_loop(_run())
        else:
            from parawave.storage import create_storage
            storage = create_storage(self._storage_name, **self._storage_kwargs)
            async def _run():
                try:
                    return await operation(storage)
                finally:
                    await storage.close()
            return run_in_event_loop(_run())

    def list_runs(
        self,
        tags: dict[str, str] | None = None,
        status: str | None = None,
    ) -> list[RunInfo]:
        return self._query(lambda s: s.list_runs(tags, status))

    def get(self, run_id: str) -> RunInfo:
        return self._query(lambda s: s.get_run_info(run_id))

    def load(self, run_id: str) -> Result:
        return self._query(lambda s: s.load_result(run_id))

    def update_tags(self, run_id: str, tags: dict[str, str]) -> None:
        self._query(lambda s: s.update_tags(run_id, tags))

    def delete(self, run_id: str) -> None:
        self._query(lambda s: s.delete_run(run_id))
