"""Centralized logging for parawave.

Singleton LogManager ensures consistent format across all modules.
Thread-safe (stdlib logging handles locking internally).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone


class _LogFormatter(logging.Formatter):
    """Parawave log formatter with local timezone timestamps."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created).astimezone()
        tz_name = dt.strftime("%Z") or "UTC"
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}"


class LogManager:
    """Singleton that configures parawave's root logger once."""

    _instance: LogManager | None = None

    def __new__(cls) -> LogManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._logger = logging.getLogger("parawave")
        level = os.environ.get("PARAWAVE_LOG_LEVEL", "WARNING").upper()
        self._logger.setLevel(getattr(logging, level, logging.INFO))

        # Only add handler if none exist (avoid duplicate handlers on re-import)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            fmt = _LogFormatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
            handler.setFormatter(fmt)
            self._logger.addHandler(handler)

    def set_level(self, level: str) -> None:
        """Update log level at runtime."""
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# Initialize on import
_manager = LogManager()


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the parawave namespace."""
    return logging.getLogger(f"parawave.{name}")
