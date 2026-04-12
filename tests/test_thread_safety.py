"""Tests for thread_safety.py."""

from __future__ import annotations

import threading

from patterns.thread_safety import (
    AtomicCounter,
    LockStrategy,
    SharedState,
    ThreadSafeQueue,
    ThreadSafetyAudit,
)


class TestLockStrategy:
    def test_mutex_has_write_contention(self):
        assert LockStrategy.MUTEX.has_write_contention() is True

    def test_none_no_contention(self):
        assert LockStrategy.NONE.has_write_contention() is False

    def test_lock_free_no_contention(self):
        assert LockStrategy.LOCK_FREE.has_write_contention() is False


class TestAtomicCounter:
    def test_initial_value(self):
        c = AtomicCounter(10)
        assert c.get() == 10

    def test_increment(self):
        c = AtomicCounter()
        c.increment()
        assert c.get() == 1

    def test_decrement(self):
        c = AtomicCounter(5)
        c.decrement()
        assert c.get() == 4

    def test_increment_returns_new_value(self):
        c = AtomicCounter(3)
        assert c.increment(2) == 5

    def test_reset(self):
        c = AtomicCounter(100)
        c.reset()
        assert c.get() == 0

    def test_compare_and_set_success(self):
        c = AtomicCounter(5)
        assert c.compare_and_set(5, 10) is True
        assert c.get() == 10

    def test_compare_and_set_fail(self):
        c = AtomicCounter(5)
        assert c.compare_and_set(99, 10) is False
        assert c.get() == 5

    def test_thread_safety(self):
        c = AtomicCounter()
        threads = [threading.Thread(target=lambda: c.increment()) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.get() == 100


class TestSharedState:
    def test_set_and_get(self):
        s = SharedState()
        s.set("key", "value")
        assert s.get("key") == "value"

    def test_get_missing_default(self):
        s = SharedState()
        assert s.get("missing", 42) == 42

    def test_delete(self):
        s = SharedState()
        s.set("k", "v")
        assert s.delete("k") is True
        assert s.get("k") is None

    def test_delete_missing(self):
        s = SharedState()
        assert s.delete("no") is False

    def test_version_increments(self):
        s = SharedState()
        v0 = s.version()
        s.set("a", 1)
        assert s.version() == v0 + 1

    def test_snapshot(self):
        s = SharedState()
        s.set("x", 1)
        snap = s.snapshot()
        s.set("x", 2)
        assert snap["x"] == 1

    def test_keys(self):
        s = SharedState()
        s.set("a", 1)
        s.set("b", 2)
        assert set(s.keys()) == {"a", "b"}

    def test_strategy_accessible(self):
        s = SharedState(LockStrategy.RW_LOCK)
        assert s.strategy == LockStrategy.RW_LOCK


class TestThreadSafeQueue:
    def test_put_and_get(self):
        q = ThreadSafeQueue()
        q.put("item")
        assert q.get() == "item"

    def test_empty_initially(self):
        q = ThreadSafeQueue()
        assert q.is_empty() is True

    def test_size(self):
        q = ThreadSafeQueue()
        q.put("a")
        q.put("b")
        assert q.size() == 2

    def test_bounded_full(self):
        q = ThreadSafeQueue(maxsize=2)
        q.put("a")
        q.put("b")
        assert q.is_full() is True

    def test_bounded_put_non_blocking_full(self):
        q = ThreadSafeQueue(maxsize=1)
        q.put("a")
        result = q.put("b", block=False)
        assert result is False

    def test_get_non_blocking_empty(self):
        q = ThreadSafeQueue()
        result = q.get(block=False)
        assert result is None

    def test_fifo_order(self):
        q = ThreadSafeQueue()
        for i in range(5):
            q.put(i)
        assert q.get() == 0


class TestThreadSafetyAudit:
    def test_initial_totals_zero(self):
        a = ThreadSafetyAudit("mymod")
        assert a.total() == 0

    def test_safety_score_empty(self):
        a = ThreadSafetyAudit("mymod")
        assert a.safety_score() == 1.0

    def test_safety_score_calculated(self):
        a = ThreadSafetyAudit("mymod", safe_count=8, unsafe_count=2)
        assert abs(a.safety_score() - 0.8) < 1e-9

    def test_is_safe_above_threshold(self):
        a = ThreadSafetyAudit("mymod", safe_count=9, unsafe_count=1)
        assert a.is_safe(threshold=0.8) is True

    def test_not_safe_below_threshold(self):
        a = ThreadSafetyAudit("mymod", safe_count=5, unsafe_count=5)
        assert a.is_safe(threshold=0.8) is False

    def test_add_note(self):
        a = ThreadSafetyAudit("mymod")
        a.add_note("check list mutations")
        assert len(a.notes) == 1

    def test_to_dict(self):
        a = ThreadSafetyAudit("mymod", safe_count=3, unsafe_count=1)
        d = a.to_dict()
        assert d["module"] == "mymod"
        assert "score" in d
