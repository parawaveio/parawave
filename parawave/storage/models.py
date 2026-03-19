"""Data models for storage records."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_SAFE_TAG_KEY = re.compile(r'^[a-zA-Z0-9_\-]+$')


def validate_tag_keys(tags: dict[str, str] | None) -> None:
    """Validate all tag keys are safe for storage backends."""
    if tags is None:
        return
    for key in tags:
        if not _SAFE_TAG_KEY.match(key):
            raise ValueError(f"Invalid tag key: {key!r}. Keys must be alphanumeric, hyphens, or underscores.")


@dataclass
class RunRecord:
    """Metadata for a parawave run."""

    run_id: str
    func_hash: str
    config: dict[str, Any]
    total_items: int
    func_name: str = ""
    tags: dict[str, str] | None = None
    created_at: str = ""
    elapsed: float = 0.0
    status: str = "running"


@dataclass
class ItemRecord:
    """Status record for a single item in a run."""

    run_id: str
    index: int
    status: str  # "completed" | "failed" | "pending"
    input_hash: str
    error: str | None
    attempts: int = 1
    elapsed: float = 0.0


@dataclass
class RunInfo:
    """Lightweight run metadata — no input/output data loaded."""

    run_id: str
    func_hash: str
    status: str
    total_items: int
    num_completed: int
    num_failed: int
    num_pending: int
    num_retried: int
    num_attempts: int
    func_name: str = ""
    tags: dict[str, str] | None = None
    created_at: datetime | None = None
    elapsed: float = 0.0

    @property
    def items_per_second(self) -> float:
        if self.elapsed <= 0:
            return 0.0
        return self.num_completed / self.elapsed

    @property
    def progress(self) -> str:
        pct = (self.num_completed / self.total_items * 100) if self.total_items else 0
        return f"{self.num_completed}/{self.total_items} ({pct:.1f}%)"

    @property
    def summary(self) -> str:
        """Same pipe-separated format as Result.summary."""
        total = self.total_items
        name = self.func_name or self.func_hash[:8]
        headline = f"{name}: {self.num_completed}/{total} completed"

        details = []
        if self.num_retried > 0:
            details.append(f"{self.num_attempts} attempts")
            details.append(f"{self.num_completed} completed")
            details.append(f"{self.num_retried} retried")
        if self.num_failed > 0:
            details.append(f"{self.num_failed} failed")
        if self.num_pending > 0:
            details.append(f"{self.num_pending} pending")

        sections = [headline]
        if details:
            sections.append(", ".join(details))
        if self.elapsed > 0:
            sections.append(f"{self.elapsed:.1f}s")
            sections.append(f"{self.items_per_second:.1f} items/s")

        return " | ".join(sections)


def hash_input(item: dict) -> str:
    """Compute SHA-256 hash of an input dict for dedup checks."""
    serialized = json.dumps(item, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
