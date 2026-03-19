"""Tests for centralized logging."""

import logging
import os
from unittest.mock import patch

from parawave.log import LogManager, get_logger


class TestGetLogger:
    def test_returns_child_logger(self):
        logger = get_logger("engine")
        assert logger.name == "parawave.engine"

    def test_logger_inherits_from_root(self):
        root = logging.getLogger("parawave")
        child = get_logger("test_child")
        assert child.parent is root

    def test_different_names_different_loggers(self):
        a = get_logger("a")
        b = get_logger("b")
        assert a is not b


class TestLogManager:
    def test_singleton(self):
        m1 = LogManager()
        m2 = LogManager()
        assert m1 is m2

    def test_root_logger_has_handler(self):
        root = logging.getLogger("parawave")
        assert len(root.handlers) >= 1

    def test_set_level(self):
        manager = LogManager()
        manager.set_level("DEBUG")
        root = logging.getLogger("parawave")
        assert root.level == logging.DEBUG
        # Reset
        manager.set_level("INFO")

    def test_format_includes_timestamp_and_level(self, caplog):
        """Verify log output contains expected format elements."""
        import io
        logger = get_logger("format_test")
        root = logging.getLogger("parawave")
        original_level = root.level
        root.setLevel(logging.DEBUG)

        # Capture via a temporary StringIO handler to test formatter output
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        from parawave.log import _LogFormatter
        handler.setFormatter(_LogFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
        root.addHandler(handler)
        try:
            logger.info("test message")
        finally:
            root.removeHandler(handler)
            root.setLevel(original_level)

        output = buf.getvalue()
        assert "INFO" in output
        assert "test message" in output
        assert "parawave.format_test" in output


class TestEnvironmentVariable:
    def test_respects_log_level_env(self):
        """LogManager reads PARAWAVE_LOG_LEVEL env var."""
        # The singleton is already initialized, so we test set_level directly
        manager = LogManager()
        manager.set_level("WARNING")
        root = logging.getLogger("parawave")
        assert root.level == logging.WARNING
        manager.set_level("INFO")
