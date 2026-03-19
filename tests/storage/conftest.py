"""Storage test fixtures."""

import pytest


@pytest.fixture
def sample_items() -> list[dict]:
    """Sample input items for storage tests."""
    return [
        {"city": "NYC"},
        {"city": "LA"},
        {"city": "Tokyo"},
    ]


@pytest.fixture
def sample_config() -> dict:
    """Sample run config for storage tests."""
    return {"max_concurrency": 10, "retry": None}
