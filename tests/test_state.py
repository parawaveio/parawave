"""Tests for SharedState — thread-safe utility."""

import threading

from parawave.state import SharedState


class TestBasicOperations:
    def test_get_set(self):
        state = SharedState()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_get_default(self):
        state = SharedState()
        assert state.get("missing") is None
        assert state.get("missing", 42) == 42

    def test_initial_state(self):
        state = SharedState({"a": 1, "b": 2})
        assert state.get("a") == 1
        assert state.get("b") == 2

    def test_increment(self):
        state = SharedState({"count": 0})
        state.increment("count")
        assert state.get("count") == 1
        state.increment("count", 5)
        assert state.get("count") == 6

    def test_increment_missing_key_starts_at_zero(self):
        state = SharedState()
        state.increment("count")
        assert state.get("count") == 1

    def test_append(self):
        state = SharedState({"items": []})
        state.append("items", "a")
        state.append("items", "b")
        assert state.get("items") == ["a", "b"]

    def test_append_missing_key_creates_list(self):
        state = SharedState()
        state.append("items", "a")
        assert state.get("items") == ["a"]

    def test_update(self):
        state = SharedState({"a": 1})
        state.update({"b": 2, "c": 3})
        assert state.get("a") == 1
        assert state.get("b") == 2
        assert state.get("c") == 3

    def test_to_dict_returns_copy(self):
        state = SharedState({"a": 1})
        d = state.to_dict()
        d["a"] = 999
        assert state.get("a") == 1


class TestLockContextManager:
    def test_lock_for_compound_operations(self):
        state = SharedState({"balance": 100})
        with state.lock():
            current = state.get("balance")
            state.set("balance", current - 30)
        assert state.get("balance") == 70


class TestThreadSafety:
    def test_concurrent_increments(self):
        state = SharedState({"count": 0})
        n_threads = 10
        n_increments = 1000

        def worker():
            for _ in range(n_increments):
                state.increment("count")

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert state.get("count") == n_threads * n_increments

    def test_concurrent_appends(self):
        state = SharedState({"items": []})
        n_threads = 10
        n_appends = 100

        def worker(thread_id: int):
            for i in range(n_appends):
                state.append("items", f"{thread_id}_{i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(state.get("items")) == n_threads * n_appends
