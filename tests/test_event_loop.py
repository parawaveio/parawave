"""Tests for event loop helper (Jupyter/notebook support)."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch, MagicMock

import pytest

from parawave._event_loop import _is_notebook, _ensure_nest_asyncio, run_in_event_loop
import parawave._event_loop as _event_loop_module


class TestIsNotebook:
    def test_not_notebook_by_default(self):
        assert _is_notebook() is False

    def test_detects_ipykernel(self):
        with patch.dict(sys.modules, {"ipykernel": MagicMock()}):
            assert _is_notebook() is True

    def test_detects_colab(self):
        with patch.dict(sys.modules, {"google.colab": MagicMock()}):
            assert _is_notebook() is True


class TestRunInEventLoop:
    def test_runs_coroutine(self):
        async def coro():
            return 42

        result = run_in_event_loop(coro())
        assert result == 42

    def test_runs_async_function(self):
        async def add(a, b):
            await asyncio.sleep(0)
            return a + b

        result = run_in_event_loop(add(3, 4))
        assert result == 7


class TestEnsureNestAsyncio:
    def setup_method(self):
        # Reset the global flag before each test
        _event_loop_module._NEST_ASYNCIO_APPLIED = False

    def teardown_method(self):
        _event_loop_module._NEST_ASYNCIO_APPLIED = False

    def test_no_op_in_standard_python(self):
        """In standard Python (no notebook, no running loop), does nothing."""
        _ensure_nest_asyncio()  # should not raise

    def test_raises_if_notebook_without_nest_asyncio(self):
        """If in notebook but nest_asyncio not installed, raises RuntimeError."""
        with patch.dict(sys.modules, {"ipykernel": MagicMock()}):
            # Mock ImportError for nest_asyncio
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def mock_import(name, *args, **kwargs):
                if name == "nest_asyncio":
                    raise ImportError("No module named 'nest_asyncio'")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                with pytest.raises(RuntimeError, match="nest_asyncio"):
                    _ensure_nest_asyncio()

    def test_idempotent_after_apply(self):
        """Once applied, doesn't apply again."""
        _event_loop_module._NEST_ASYNCIO_APPLIED = True
        # Should return immediately without error even in notebook context
        with patch.dict(sys.modules, {"ipykernel": MagicMock()}):
            _ensure_nest_asyncio()  # should not raise
