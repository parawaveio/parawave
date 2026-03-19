"""Integration tests — resume and recovery scenarios."""

import parawave
from parawave import RetryPolicy
from tests.helpers import make_fail_n_then_succeed, make_failing_for, make_city_data


class TestResumeSameSession:
    def test_resume_retries_failed(self):
        """First run partially fails, resume retries and completes."""
        calls = {"n": 0}

        async def process(city: str) -> str:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise ValueError("transient")
            return f"processed {city}"

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def wrapped(city: str) -> str:
            return await process(city=city)

        result1 = wrapped.run(data=[{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}])
        # First 2 fail, third succeeds
        assert not result1.ok
        assert len(result1.failed) == 2
        assert len(result1.completed) == 1

        # Resume — the function no longer fails
        result2 = wrapped.resume()
        assert result2.ok is True
        assert result2.summary.startswith("3/3 completed")

    def test_resume_result_is_complete_snapshot(self):
        """After resume, result includes ALL items, not just retried ones."""
        calls = {"n": 0}

        async def process(city: str) -> str:
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValueError("fail LA only")
            return f"processed {city}"

        @parawave(max_concurrency=1, storage="in_memory", progress=None)
        async def wrapped(city: str) -> str:
            return await process(city=city)

        result1 = wrapped.run(data=[{"city": "NYC"}, {"city": "LA"}, {"city": "Tokyo"}])
        assert len(result1) == 3  # always full length

        result2 = wrapped.resume()
        assert len(result2) == 3  # still full length after resume


class TestRetryWithPolicy:
    def test_retry_policy_recovers(self):
        fn = make_fail_n_then_succeed(2)

        @parawave(
            max_concurrency=1,
            retry=RetryPolicy(max_retries=3, backoff="fixed", base_delay=0.01),
            storage="in_memory",
            progress=None,
        )
        async def process(city: str) -> str:
            return await fn(city=city)

        result = process.run(data=[{"city": "NYC"}])
        assert result.ok is True


class TestDryRun:
    def test_dry_run_single_item(self):
        @parawave(
            max_concurrency=10,
            retry=RetryPolicy(max_retries=3),
            rate_limit=100,
            storage="in_memory",
            progress=None,
        )
        async def process(city: str) -> str:
            return f"processed {city}"

        result = process.dry_run(data=[{"city": "NYC"}])
        assert result.ok is True
        assert result[0].output == "processed NYC"
