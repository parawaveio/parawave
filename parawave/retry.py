"""RetryPolicy — configuration for retry behavior."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetryPolicy:
    """Configures retry behavior for failed items.

    Args:
        max_retries: Maximum retry attempts per item.
        backoff: Backoff strategy — "fixed", "exponential", or "exponential_jitter".
        base_delay: Base delay in seconds between retries.
        max_delay: Maximum delay cap for exponential backoff.
        retryable: Only retry these exception types. Mutually exclusive with non_retryable.
        non_retryable: Never retry these exception types. Mutually exclusive with retryable.
    """

    max_retries: int = 0
    backoff: str = "exponential"
    base_delay: float = 1.0
    max_delay: float = 60.0
    retryable: list[type[Exception]] | None = field(default=None, repr=False)
    non_retryable: list[type[Exception]] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.retryable is not None and self.non_retryable is not None:
            raise ValueError("Provide retryable or non_retryable, not both")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff not in ("fixed", "exponential", "exponential_jitter"):
            raise ValueError(f"Invalid backoff strategy: {self.backoff!r}")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")

    def should_retry(self, exception: Exception) -> bool:
        """Check whether the given exception should trigger a retry."""
        if self.retryable is not None:
            return isinstance(exception, tuple(self.retryable))
        if self.non_retryable is not None:
            return not isinstance(exception, tuple(self.non_retryable))
        return True

    def get_delay(self, attempt: int) -> float:
        """Calculate delay in seconds for the given attempt number (0-indexed)."""
        if self.backoff == "fixed":
            return self.base_delay
        elif self.backoff == "exponential":
            delay = self.base_delay * (2 ** attempt)
            return min(delay, self.max_delay)
        else:  # exponential_jitter
            delay = self.base_delay * (2 ** attempt)
            delay = min(delay, self.max_delay)
            return delay * random.uniform(0.5, 1.5)
