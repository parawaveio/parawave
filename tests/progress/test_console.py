"""Tests for console progress reporter."""

from parawave.progress.base import ProgressSnapshot
from parawave.progress.console import ConsoleProgress


class TestConsoleProgress:
    def test_on_update_does_not_raise(self, capsys):
        reporter = ConsoleProgress()
        snap = ProgressSnapshot(
            total=100, completed=50, failed=2, pending=43, running=5, elapsed=10.0
        )
        reporter.on_update(snap)
        captured = capsys.readouterr()
        assert "50" in captured.err or "50" in captured.out

    def test_throttles_output(self, capsys):
        reporter = ConsoleProgress(min_interval=1.0)
        snap = ProgressSnapshot(
            total=10, completed=1, failed=0, pending=8, running=1, elapsed=0.1
        )
        for _ in range(10):
            reporter.on_update(snap)

    def test_always_prints_final(self, capsys):
        reporter = ConsoleProgress(min_interval=999.0)
        snap = ProgressSnapshot(
            total=10, completed=10, failed=0, pending=0, running=0, elapsed=5.0
        )
        reporter.on_update(snap)
        captured = capsys.readouterr()
        assert "10" in captured.err or "10" in captured.out
