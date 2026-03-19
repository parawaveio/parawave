"""Event loop helper — handles Jupyter notebooks, Google Colab, and standard Python."""

from __future__ import annotations

import asyncio
import sys

from parawave.log import get_logger

logger = get_logger(__name__)

_NEST_ASYNCIO_APPLIED = False


def _is_notebook() -> bool:
    """Detect if running inside a Jupyter notebook or Google Colab."""
    return "ipykernel" in sys.modules or "google.colab" in sys.modules


def _ensure_nest_asyncio() -> None:
    """Apply nest_asyncio if running in a notebook or existing event loop."""
    global _NEST_ASYNCIO_APPLIED
    if _NEST_ASYNCIO_APPLIED:
        return

    try:
        loop = asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    if _is_notebook() or loop_running:
        try:
            import nest_asyncio

            nest_asyncio.apply()
            _NEST_ASYNCIO_APPLIED = True
            logger.debug("nest_asyncio applied for nested event loop support")
        except ImportError:
            raise RuntimeError(
                "Jupyter/Colab support requires one lightweight package: nest_asyncio. "
                "Install with: pip install parawave[notebook]"
            )


def run_in_event_loop(coroutine):
    """Run an async coroutine from sync context.

    Handles Jupyter notebooks, Google Colab, and standard Python.
    When a loop is already running (Jupyter), uses run_until_complete()
    which nest_asyncio patches to allow reentrant calls.
    """
    _ensure_nest_asyncio()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    # Loop is already running (notebook) — use nest_asyncio's patched run_until_complete
    return loop.run_until_complete(coroutine)
