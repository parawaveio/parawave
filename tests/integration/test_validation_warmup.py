"""Integration tests for input/output validation and warmup mode."""

import pytest

from parawave.decorator import parawave
from parawave.errors import ValidationError


class TestValidationWarmupIntegration:
    def test_full_pipeline_happy_path_with_warmup(self):
        """Valid inputs + valid function + warmup → full successful run."""
        @parawave(max_concurrency=3, storage="in_memory", warmup=True)
        async def process(city: str) -> str:
            return f"processed {city}"

        result = process.run(
            data=[{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}]
        )
        assert result.ok is True
        assert result.num_completed == 3

    def test_non_serializable_input_blocks_run(self):
        """Non-serializable input → ValidationError before any execution."""
        call_count = {"n": 0}

        @parawave(storage="in_memory")
        async def process(data) -> str:
            call_count["n"] += 1
            return "ok"

        with pytest.raises(ValidationError, match="not JSON-serializable"):
            process.run(data=[{"data": b"binary"}])

        assert call_count["n"] == 0

    def test_non_serializable_output_caught_by_warmup(self):
        """Valid input + non-serializable output → warmup catches it."""
        @parawave(max_concurrency=5, storage="in_memory", warmup=True)
        async def process(x: int):
            return b"binary output"

        result = process.run(data=[{"x": i} for i in range(10)])
        assert result.ok is False
        assert result[0].status == "failed"
        assert "not JSON-serializable" in result[0].error
        assert result.num_pending == 9

    def test_resume_after_warmup_failure(self):
        """Resume after warmup failure should process all items."""
        attempts = {"n": 0}

        @parawave(storage="in_memory", warmup=True)
        async def process(x: int) -> int:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("first call fails")
            return x * 2

        # First run: warmup fails
        result = process.run(data=[{"x": 1}, {"x": 2}, {"x": 3}])
        assert result.ok is False
        assert result[0].status == "failed"

        # Resume without warmup (default) — should retry all
        result = process.resume()
        assert result.ok is True
        assert result.num_completed == 3

    def test_warmup_disabled_processes_all(self):
        """warmup=False should process all items even if some fail."""
        @parawave(max_concurrency=5, storage="in_memory")
        async def process(x: int) -> int:
            if x == 0:
                raise ValueError("item 0 fails")
            return x * 2

        result = process.run(data=[{"x": i} for i in range(5)])
        assert result.ok is False
        assert result[0].status == "failed"
        assert result.num_completed == 4  # items 1-4 succeeded

    def test_warmup_override_at_runtime(self):
        """warmup can be overridden at .run() time."""
        @parawave(max_concurrency=5, storage="in_memory")
        async def process(x: int) -> int:
            return x * 2

        # Default warmup=False from decorator, override to True at runtime
        result = process.run(data=[{"x": 1}, {"x": 2}], warmup=True)
        assert result.ok is True
        assert result.num_completed == 2
