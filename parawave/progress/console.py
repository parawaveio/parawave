"""Console progress reporter — default, no dependencies."""

from __future__ import annotations

import sys
import time

from parawave.progress.base import ProgressSnapshot


class ConsoleProgress:
    """Prints periodic progress lines to stderr."""

    def __init__(self, min_interval: float = 0.5) -> None:
        self._min_interval = min_interval
        self._last_print = 0.0

    def on_update(self, snapshot: ProgressSnapshot) -> None:
        now = time.monotonic()
        is_final = (snapshot.completed + snapshot.failed) >= snapshot.total

        if not is_final and (now - self._last_print) < self._min_interval:
            return

        self._last_print = now
        finished = snapshot.completed + snapshot.failed
        parts = [f"{snapshot.completed} completed"]
        if snapshot.failed:
            parts.append(f"{snapshot.failed} failed")
        if snapshot.retries:
            parts.append(f"{snapshot.retries} retried")

        line = f"[parawave] {finished}/{snapshot.total} ({', '.join(parts)})"
        if snapshot.elapsed > 0:
            line += f" | {snapshot.elapsed:.1f}s | {snapshot.items_per_second:.1f} items/s"
        print(line, file=sys.stderr, flush=True)
