"""Tests verifying dependency isolation.

These tests verify the public API works correctly regardless of
which optional dependencies are installed.
"""

import pytest
import inspect


class TestZeroDepsImport:
    def test_parawave_importable(self):
        """Core package should be importable."""
        import parawave
        assert hasattr(parawave, '__all__')

    def test_all_exports_importable(self):
        """All __all__ exports should be importable with zero deps."""
        from parawave import (
            RetryPolicy, SharedState, RunManager,
            Result, ResultItem, Storage,
        )
        assert RetryPolicy is not None
        assert Storage is not None
        assert Result is not None
        assert ResultItem is not None
        assert RunManager is not None
        assert SharedState is not None


class TestSqliteStorageRegistry:
    def test_sqlite_in_registry(self):
        """sqlite backend should be registered."""
        from parawave.storage import _REGISTRY
        assert "sqlite" in _REGISTRY

    def test_in_memory_in_registry(self):
        """in_memory backend should be registered."""
        from parawave.storage import _REGISTRY
        assert "in_memory" in _REGISTRY


class TestNotebookErrorMessage:
    def test_event_loop_error_mentions_install(self):
        """Notebook path error should mention pip install parawave[notebook]."""
        from parawave._event_loop import _ensure_nest_asyncio
        source = inspect.getsource(_ensure_nest_asyncio)
        assert "pip install parawave[notebook]" in source


class TestProgressFallback:
    def test_bar_falls_back_to_console(self):
        """progress='bar' without tqdm should fall back gracefully."""
        from parawave.progress.bar import create_bar_progress
        progress = create_bar_progress(10)
        assert progress is not None

    def test_tqdm_warning_message(self):
        """Tqdm fallback warning should say 'pip install tqdm'."""
        from parawave.progress import bar
        source = inspect.getsource(bar)
        assert "pip install tqdm" in source
