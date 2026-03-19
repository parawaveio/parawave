"""Tests for parawave custom exceptions."""

from parawave.errors import (
    ParawaveError,
    ValidationError,
    StorageError,
    RunNotFoundError,
    DuplicateRunError,
    ShutdownRequested,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_parawave_error(self):
        for exc_class in [ValidationError, StorageError, RunNotFoundError, DuplicateRunError]:
            assert issubclass(exc_class, ParawaveError)

    def test_parawave_error_inherits_from_exception(self):
        assert issubclass(ParawaveError, Exception)

    def test_shutdown_requested_is_base_exception(self):
        assert issubclass(ShutdownRequested, BaseException)
        assert not issubclass(ShutdownRequested, Exception)

    def test_run_not_found_inherits_storage_error(self):
        assert issubclass(RunNotFoundError, StorageError)

    def test_duplicate_run_inherits_validation_error(self):
        assert issubclass(DuplicateRunError, ValidationError)


class TestExceptionMessages:
    def test_validation_error_message(self):
        err = ValidationError("bad input")
        assert str(err) == "bad input"

    def test_run_not_found_message(self):
        err = RunNotFoundError("run-abc123")
        assert "run-abc123" in str(err)

    def test_exceptions_can_be_raised_and_caught(self):
        try:
            raise ValidationError("test")
        except ParawaveError as e:
            assert str(e) == "test"
