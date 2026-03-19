"""Hook execution — fire lifecycle callbacks safely."""

from __future__ import annotations

from parawave.log import get_logger
from typing import Any, Callable

logger = get_logger(__name__)


def fire_hooks(hooks: list[Callable], *args: Any) -> None:
    """Fire a list of hook callbacks with the given arguments.

    Hook errors are logged as warnings and swallowed — they never
    crash the run or affect item outcomes.
    """
    for hook in hooks:
        try:
            hook(*args)
        except Exception:
            hook_name = getattr(hook, "__name__", repr(hook))
            logger.warning("Hook %s raised an exception", hook_name, exc_info=True)
