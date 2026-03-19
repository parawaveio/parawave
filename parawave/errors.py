"""Custom exceptions for parawave."""

from __future__ import annotations


class ParawaveError(Exception):
    """Base exception for all parawave errors."""


class ValidationError(ParawaveError):
    """Raised for input/configuration validation failures."""


class StorageError(ParawaveError):
    """Raised for storage operation failures."""


class RunNotFoundError(StorageError):
    """Raised when a run ID is not found in storage."""

    def __init__(self, run_id: str, message: str | None = None) -> None:
        super().__init__(message or f"Run not found: {run_id}")
        self.run_id = run_id


class DuplicateRunError(ValidationError):
    """Raised when a user-provided run ID already exists."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"Run ID '{run_id}' already exists. Use .resume('{run_id}') to continue it."
        )
        self.run_id = run_id


class ShutdownRequested(BaseException):
    """Raised to signal graceful shutdown.

    Inherits BaseException (not Exception) so it won't be caught
    by user code's bare `except Exception` handlers.
    """
