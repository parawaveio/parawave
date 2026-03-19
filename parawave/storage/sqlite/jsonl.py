"""JSONL file store for input/output data payloads."""

from __future__ import annotations

import json
from parawave.log import get_logger
from pathlib import Path
from typing import Any

import aiofiles

logger = get_logger(__name__)


class JsonlStore:
    """Stores input and output data as JSONL files.

    Directory layout:
        {run_dir}/inputs.jsonl   — one JSON line per input item (written once)
        {run_dir}/outputs.jsonl  — one JSON line per output: {"index": i, "data": ...}
    """

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir
        self._inputs_path = run_dir / "inputs.jsonl"
        self._outputs_path = run_dir / "outputs.jsonl"

    async def write_inputs(self, items: list[dict]) -> None:
        """Write all input items to inputs.jsonl (called once at run creation)."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._inputs_path, "w") as f:
            for item in items:
                await f.write(json.dumps(item) + "\n")

    async def read_input(self, index: int) -> dict:
        """Read input item at given index."""
        async with aiofiles.open(self._inputs_path, "r") as f:
            lines = await f.readlines()
        return json.loads(lines[index])

    async def write_output(self, index: int, output: Any) -> None:
        """Append an output entry to outputs.jsonl."""
        self._run_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps({"index": index, "data": output})
        async with aiofiles.open(self._outputs_path, "a") as f:
            await f.write(serialized + "\n")

    async def read_output(self, index: int) -> Any | None:
        """Read output for a given index. Returns the latest entry (handles retries)."""
        if not self._outputs_path.exists():
            return None

        async with aiofiles.open(self._outputs_path, "r") as f:
            lines = await f.readlines()

        # Return last match — on retry, a new entry is appended for the same index
        result = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping corrupt output line in %s", self._outputs_path)
                continue
            if entry["index"] == index:
                result = entry["data"]
        return result
