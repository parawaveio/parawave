"""Progress callback protocol and snapshot dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ProgressSnapshot:
    """Point-in-time snapshot of run progress."""

    total: int
    completed: int
    failed: int
    pending: int
    running: int
    elapsed: float
    retries: int = 0

    @property
    def items_per_second(self) -> float:
        """Throughput: finished items per second."""
        finished = self.completed + self.failed
        if self.elapsed <= 0:
            return 0.0
        return finished / self.elapsed


class ProgressCallback(Protocol):
    """Protocol for progress reporters."""

    def on_update(self, snapshot: ProgressSnapshot) -> None: ...
