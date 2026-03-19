"""tqdm-based progress bar — optional dependency."""

from __future__ import annotations

from parawave.log import get_logger

from parawave.progress.base import ProgressCallback, ProgressSnapshot

logger = get_logger(__name__)

try:
    from tqdm import tqdm as _tqdm

    class BarProgress:
        """tqdm progress bar reporter."""

        def __init__(self, total: int) -> None:
            self._bar = _tqdm(total=total, desc="parawave", unit="item")
            self._last_n = 0

        def on_update(self, snapshot: ProgressSnapshot) -> None:
            finished = snapshot.completed + snapshot.failed
            delta = finished - self._last_n
            if delta > 0:
                self._bar.update(delta)
                self._last_n = finished
            if finished >= snapshot.total:
                self._bar.close()

    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False


def create_bar_progress(total: int) -> ProgressCallback:
    """Create a bar progress reporter, falling back to console if tqdm is missing."""
    if _HAS_TQDM:
        return BarProgress(total)
    else:
        logger.warning("tqdm not installed, falling back to console progress. Install with: pip install tqdm")
        from parawave.progress.console import ConsoleProgress
        return ConsoleProgress()
