"""Two-phase graceful shutdown handler."""

from __future__ import annotations

import signal
import sys
from typing import Any


class ShutdownHandler:
    """Manages two-phase shutdown via signal handling.

    First Ctrl+C: graceful — stop accepting new items, wait for in-flight.
    Second Ctrl+C: force — cancel all tasks immediately.
    """

    def __init__(self) -> None:
        self._interrupt_count = 0
        self._original_handler: Any = None

    @property
    def should_stop(self) -> bool:
        return self._interrupt_count >= 1

    @property
    def force_stop(self) -> bool:
        return self._interrupt_count >= 2

    def request_shutdown(self) -> None:
        """Called on each interrupt signal."""
        self._interrupt_count += 1
        if self._interrupt_count == 1:
            print(
                "\n[parawave] Interrupt received. Waiting for in-flight tasks...",
                file=sys.stderr,
                flush=True,
            )
        elif self._interrupt_count >= 2:
            print(
                "\n[parawave] Force shutdown. Cancelling all tasks.",
                file=sys.stderr,
                flush=True,
            )

    def force_shutdown(self) -> None:
        """Trigger immediate force stop (equivalent to second Ctrl+C)."""
        self._interrupt_count = 2
        print(
            "\n[parawave] Force shutdown. Cancelling all tasks.",
            file=sys.stderr,
            flush=True,
        )

    def install(self) -> None:
        """Install signal handlers for SIGINT and SIGTERM."""
        self._original_handler = signal.getsignal(signal.SIGINT)
        self._original_sigterm_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def uninstall(self) -> None:
        """Restore original signal handlers."""
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)
            self._original_handler = None
        if hasattr(self, "_original_sigterm_handler") and self._original_sigterm_handler is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)
            self._original_sigterm_handler = None

    def reset(self) -> None:
        """Reset state (for testing)."""
        self._interrupt_count = 0

    def _handle_signal(self, signum: int, frame: Any) -> None:
        self.request_shutdown()
