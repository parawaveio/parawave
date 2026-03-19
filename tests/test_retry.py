"""Tests for RetryPolicy."""

import pytest

from parawave.retry import RetryPolicy


class TestRetryPolicyConstruction:
    def test_defaults(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.max_retries == 3
        assert policy.backoff == "exponential"
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.retryable is None
        assert policy.non_retryable is None

    def test_custom_values(self):
        policy = RetryPolicy(
            max_retries=5,
            backoff="fixed",
            base_delay=2.0,
            max_delay=30.0,
            retryable=[ValueError],
        )
        assert policy.max_retries == 5
        assert policy.backoff == "fixed"
        assert policy.base_delay == 2.0
        assert policy.max_delay == 30.0
        assert policy.retryable == [ValueError]

    def test_zero_retries(self):
        policy = RetryPolicy(max_retries=0)
        assert policy.max_retries == 0


class TestRetryPolicyValidation:
    def test_both_retryable_and_non_retryable_raises(self):
        with pytest.raises(ValueError, match="retryable.*non_retryable"):
            RetryPolicy(max_retries=3, retryable=[ValueError], non_retryable=[TypeError])

    def test_negative_max_retries_raises(self):
        with pytest.raises(ValueError, match="max_retries"):
            RetryPolicy(max_retries=-1)

    def test_invalid_backoff_raises(self):
        with pytest.raises(ValueError, match="backoff"):
            RetryPolicy(max_retries=3, backoff="invalid")

    def test_non_positive_base_delay_raises(self):
        with pytest.raises(ValueError, match="base_delay"):
            RetryPolicy(max_retries=3, base_delay=0)

    def test_max_delay_less_than_base_delay_raises(self):
        with pytest.raises(ValueError, match="max_delay"):
            RetryPolicy(max_retries=3, base_delay=10, max_delay=5)


class TestShouldRetry:
    def test_no_filters_retries_all(self):
        policy = RetryPolicy(max_retries=3)
        assert policy.should_retry(ValueError("test")) is True
        assert policy.should_retry(TypeError("test")) is True
        assert policy.should_retry(RuntimeError("test")) is True

    def test_retryable_list(self):
        policy = RetryPolicy(max_retries=3, retryable=[ValueError, TypeError])
        assert policy.should_retry(ValueError("test")) is True
        assert policy.should_retry(TypeError("test")) is True
        assert policy.should_retry(RuntimeError("test")) is False

    def test_non_retryable_list(self):
        policy = RetryPolicy(max_retries=3, non_retryable=[ValueError])
        assert policy.should_retry(ValueError("test")) is False
        assert policy.should_retry(TypeError("test")) is True
        assert policy.should_retry(RuntimeError("test")) is True

    def test_subclass_matching(self):
        class CustomValueError(ValueError):
            pass
        policy = RetryPolicy(max_retries=3, retryable=[ValueError])
        assert policy.should_retry(CustomValueError("test")) is True


class TestGetDelay:
    def test_fixed_backoff(self):
        policy = RetryPolicy(max_retries=3, backoff="fixed", base_delay=2.0)
        assert policy.get_delay(0) == 2.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(5) == 2.0

    def test_exponential_backoff(self):
        policy = RetryPolicy(max_retries=5, backoff="exponential", base_delay=1.0)
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 4.0
        assert policy.get_delay(3) == 8.0

    def test_exponential_capped_at_max_delay(self):
        policy = RetryPolicy(max_retries=10, backoff="exponential", base_delay=1.0, max_delay=10.0)
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(3) == 8.0
        assert policy.get_delay(4) == 10.0
        assert policy.get_delay(10) == 10.0

    def test_exponential_jitter_within_range(self):
        policy = RetryPolicy(max_retries=3, backoff="exponential_jitter", base_delay=1.0, max_delay=60.0)
        for attempt in range(4):
            base = min(1.0 * (2 ** attempt), 60.0)
            for _ in range(20):
                delay = policy.get_delay(attempt)
                assert base * 0.5 <= delay <= base * 1.5, f"delay {delay} outside jitter range for attempt {attempt}"


class TestRetryPolicyImmutable:
    def test_frozen(self):
        policy = RetryPolicy(max_retries=3)
        with pytest.raises(AttributeError):
            policy.max_retries = 5
