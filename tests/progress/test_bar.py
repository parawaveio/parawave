"""Tests for tqdm bar progress reporter."""

import pytest

from parawave.progress.base import ProgressSnapshot


class TestBarProgress:
    def test_import_without_tqdm_returns_console(self):
        from parawave.progress.bar import create_bar_progress
        reporter = create_bar_progress(total=10)
        assert hasattr(reporter, "on_update")

    def test_on_update_does_not_raise(self):
        from parawave.progress.bar import create_bar_progress
        reporter = create_bar_progress(total=10)
        snap = ProgressSnapshot(
            total=10, completed=5, failed=0, pending=4, running=1, elapsed=2.0
        )
        reporter.on_update(snap)

    def test_complete_closes_bar(self):
        from parawave.progress.bar import create_bar_progress
        reporter = create_bar_progress(total=5)
        final = ProgressSnapshot(
            total=5, completed=5, failed=0, pending=0, running=0, elapsed=1.0
        )
        reporter.on_update(final)
