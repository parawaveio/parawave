"""Tests for hook execution."""

import logging

from parawave.hooks import fire_hooks
from parawave.result import ResultItem


class TestFireHooks:
    def test_single_hook(self):
        calls = []
        def on_start(run_id, total_items):
            calls.append(("start", run_id, total_items))
        fire_hooks([on_start], "run-1", 100)
        assert calls == [("start", "run-1", 100)]

    def test_multiple_hooks_in_order(self):
        order = []
        def hook_a(run_id, total):
            order.append("a")
        def hook_b(run_id, total):
            order.append("b")
        fire_hooks([hook_a, hook_b], "run-1", 10)
        assert order == ["a", "b"]

    def test_hook_error_swallowed(self, caplog):
        def bad_hook(run_id, total):
            raise ValueError("hook failed")
        def good_hook(run_id, total):
            pass
        with caplog.at_level(logging.WARNING):
            fire_hooks([bad_hook, good_hook], "run-1", 10)
        assert "hook failed" in caplog.text

    def test_empty_hooks_list(self):
        fire_hooks([], "run-1", 10)

    def test_item_hook(self):
        calls = []
        def on_item(item: ResultItem):
            calls.append(item.index)
        item = ResultItem(index=5, input={}, output="ok", status="completed", error=None)
        fire_hooks([on_item], item)
        assert calls == [5]
