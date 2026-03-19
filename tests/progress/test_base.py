"""Tests for ProgressSnapshot."""

from parawave.progress.base import ProgressSnapshot


class TestProgressSnapshot:
    def test_construction(self):
        snap = ProgressSnapshot(
            total=100, completed=80, failed=5, pending=10, running=5, elapsed=30.0
        )
        assert snap.total == 100
        assert snap.completed == 80
        assert snap.failed == 5
        assert snap.pending == 10
        assert snap.running == 5
        assert snap.elapsed == 30.0

    def test_items_per_second(self):
        snap = ProgressSnapshot(
            total=100, completed=80, failed=5, pending=10, running=5, elapsed=20.0
        )
        assert snap.items_per_second == (80 + 5) / 20.0

    def test_items_per_second_zero_elapsed(self):
        snap = ProgressSnapshot(
            total=10, completed=0, failed=0, pending=10, running=0, elapsed=0.0
        )
        assert snap.items_per_second == 0.0
