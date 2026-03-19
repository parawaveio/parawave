"""Result and ResultItem — index-aligned result container."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ResultItem:
    """A single item's result within a parawave run.

    Attributes:
        index: Original position in input list.
        input: The original input dict.
        output: Function return value if completed, else None.
        status: One of "completed", "failed", "pending".
        error: Error message if failed, else None.
        attempts: Number of times the function was called (1 = first try worked).
    """

    index: int
    input: dict
    output: Any | None
    status: str
    error: str | None
    attempts: int = 1
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """True if this item completed successfully."""
        return self.status == "completed"

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for inspection or serialization."""
        d = dataclasses.asdict(self)
        d["ok"] = self.ok
        return d

    def to_json(self, indent: int | None = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class Result:
    """Index-aligned result container for a parawave run.

    Always the same length as the input, same order.
    Every item is accounted for with a status.
    """

    def __init__(
        self,
        items: list[ResultItem],
        run_id: str,
        elapsed: float = 0.0,
        tags: dict[str, str] | None = None,
    ) -> None:
        self._items = items
        self.run_id = run_id
        self.elapsed = elapsed
        self.tags = tags

    @property
    def ok(self) -> bool:
        """True if all items completed successfully."""
        return all(item.ok for item in self._items)

    @property
    def num_items(self) -> int:
        """Total number of input items (requests)."""
        return len(self._items)

    @property
    def num_completed(self) -> int:
        """Count of items that completed successfully."""
        return sum(1 for item in self._items if item.status == "completed")

    @property
    def num_failed(self) -> int:
        """Count of items that failed after all retries."""
        return sum(1 for item in self._items if item.status == "failed")

    @property
    def num_pending(self) -> int:
        """Count of items that never ran."""
        return sum(1 for item in self._items if item.status == "pending")

    @property
    def num_retried(self) -> int:
        """Count of items that needed more than one attempt."""
        return sum(1 for item in self._items if item.attempts > 1)

    @property
    def num_attempts(self) -> int:
        """Total number of attempts across all items."""
        return sum(item.attempts for item in self._items)

    @property
    def items_per_second(self) -> float:
        """Throughput: completed items per second."""
        if self.elapsed <= 0:
            return 0.0
        return self.num_completed / self.elapsed

    @property
    def avg_item_elapsed(self) -> float:
        """Average elapsed time per completed item."""
        completed = [item for item in self._items if item.ok]
        if not completed:
            return 0.0
        return sum(item.elapsed for item in completed) / len(completed)

    @property
    def summary(self) -> str:
        """Human-readable summary.

        Format: headline | details | elapsed | throughput
        Examples:
            30/30 completed | 3.5s | 8.6 items/s
            28/30 completed | 2 failed | 3.5s | 8.0 items/s
            28/30 completed | 38 attempts, 28 completed, 5 retried, 2 failed | 3.5s | 8.0 items/s
        """
        total = len(self._items)
        headline = f"{self.num_completed}/{total} completed"

        has_retries = self.num_retried > 0
        has_failures = self.num_failed > 0
        has_pending = self.num_pending > 0

        # Build detail section
        details = []
        if has_retries:
            details.append(f"{self.num_attempts} attempts")
            details.append(f"{self.num_completed} completed")
            details.append(f"{self.num_retried} retried")
        if has_failures:
            details.append(f"{self.num_failed} failed")
        if has_pending:
            details.append(f"{self.num_pending} pending")

        sections = [headline]
        if details:
            sections.append(", ".join(details))
        if self.elapsed > 0:
            sections.append(f"{self.elapsed:.1f}s")
            sections.append(f"{self.items_per_second:.1f} items/s")

        return " | ".join(sections)

    @property
    def data(self) -> list[Any]:
        """Flat output list — None for failed/pending items."""
        return [item.output if item.ok else None for item in self._items]

    @property
    def completed(self) -> list[ResultItem]:
        """Items that completed successfully."""
        return [item for item in self._items if item.status == "completed"]

    @property
    def failed(self) -> list[ResultItem]:
        """Items that failed after all retries."""
        return [item for item in self._items if item.status == "failed"]

    @property
    def pending(self) -> list[ResultItem]:
        """Items that never ran."""
        return [item for item in self._items if item.status == "pending"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for inspection or serialization."""
        return {
            "run_id": self.run_id,
            "ok": self.ok,
            "summary": self.summary,
            "num_items": self.num_items,
            "num_completed": self.num_completed,
            "num_failed": self.num_failed,
            "num_pending": self.num_pending,
            "num_retried": self.num_retried,
            "num_attempts": self.num_attempts,
            "elapsed": self.elapsed,
            "items_per_second": self.items_per_second,
            "tags": self.tags,
            "items": [item.to_dict() for item in self._items],
        }

    def to_json(self, indent: int | None = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_csv(self, path: str | None = None) -> str:
        """Export results as CSV.

        One row per item. Columns: index, status, input, output, error, attempts, elapsed, ok.

        Args:
            path: If provided, writes to file and returns the path.
                  If None, returns CSV as a string.
        """
        import csv
        import io

        fieldnames = ["index", "status", "input", "output", "error", "attempts", "elapsed", "ok"]

        def _write(writer):
            writer.writeheader()
            for item in self._items:
                writer.writerow({
                    "index": item.index,
                    "status": item.status,
                    "input": json.dumps(item.input, default=str),
                    "output": json.dumps(item.output, default=str) if item.output is not None else "",
                    "error": item.error or "",
                    "attempts": item.attempts,
                    "elapsed": item.elapsed,
                    "ok": item.ok,
                })

        if path is not None:
            with open(path, "w", newline="") as f:
                _write(csv.DictWriter(f, fieldnames=fieldnames))
            return path

        buf = io.StringIO()
        _write(csv.DictWriter(buf, fieldnames=fieldnames))
        return buf.getvalue()

    def __repr__(self) -> str:
        return f"Result({self.summary})"

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int | slice) -> ResultItem | list[ResultItem]:
        return self._items[index]

    def __iter__(self):
        return iter(self._items)
