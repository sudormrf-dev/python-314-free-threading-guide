"""Practical migration guide: GIL-dependent code → free-threading safe.

Five concrete before/after patterns with runnable verification.

Patterns covered:
  1. Unsynchronized global counter  → AtomicCounter
  2. Shared mutable dict            → SharedState with lock
  3. Lazy singleton (DCL)           → module-level or threading.local
  4. Unprotected list accumulator   → queue.Queue / locked list
  5. Read-modify-write on cache     → compare_and_set CAS loop
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patterns.thread_safety import AtomicCounter, LockStrategy, SharedState

_SEP = "=" * 64
_SUB = "-" * 64
_N_THREADS = 8
_N_OPS = 200


# ---------------------------------------------------------------------------
# Pattern 1: unsynchronized global counter → AtomicCounter
# ---------------------------------------------------------------------------

_old_counter = 0


def _old_increment() -> None:
    """Before: plain global — broken under free-threading."""
    global _old_counter
    _old_counter += 1  # NOT atomic: LOAD_FAST + BINARY_ADD + STORE_FAST


def pattern1_before() -> int:
    """Run the broken version; return final value."""
    global _old_counter
    _old_counter = 0
    threads = [
        threading.Thread(target=_old_increment) for _ in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return _old_counter


def pattern1_after() -> int:
    """Run the fixed version with AtomicCounter; return final value."""
    counter = AtomicCounter(0)
    threads = [
        threading.Thread(target=counter.increment) for _ in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter.get()


# ---------------------------------------------------------------------------
# Pattern 2: shared mutable dict → SharedState
# ---------------------------------------------------------------------------

_old_registry: dict[str, int] = {}
_new_registry = SharedState(strategy=LockStrategy.MUTEX)


def _old_register(key: str, value: int) -> None:
    """Before: unprotected dict write."""
    _old_registry[key] = value  # dict assignment is NOT guaranteed atomic


def _new_register(key: str, value: int) -> None:
    """After: SharedState serializes writes with an RLock."""
    _new_registry.set(key, value)


def pattern2_before() -> int:
    """Populate a shared dict from multiple threads — may lose entries."""
    _old_registry.clear()
    threads = [
        threading.Thread(target=_old_register, args=(f"key{i}", i))
        for i in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(_old_registry)


def pattern2_after() -> int:
    """Populate SharedState from multiple threads — no lost entries."""
    threads = [
        threading.Thread(target=_new_register, args=(f"key{i}", i))
        for i in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(_new_registry.snapshot())


# ---------------------------------------------------------------------------
# Pattern 3: lazy singleton (double-checked locking) → safe init
# ---------------------------------------------------------------------------

_bad_singleton: dict[str, Any] | None = None  # DCL broken without GIL


def _get_bad_singleton() -> dict[str, Any]:
    """Before: double-checked locking — BROKEN under free-threading."""
    global _bad_singleton
    if _bad_singleton is None:  # check 1 — not protected
        # another thread can reach here simultaneously
        if _bad_singleton is None:  # check 2 — still racy
            _bad_singleton = {"initialized": True}
    return _bad_singleton  # type: ignore[return-value]


# After: initialize at module level — Python guarantees module import is serialized
_good_singleton: dict[str, Any] = {"initialized": True}


def _get_good_singleton() -> dict[str, Any]:
    """After: module-level object — safe, no lock needed."""
    return _good_singleton


_singleton_lock = threading.Lock()
_locked_singleton: dict[str, Any] | None = None


def _get_locked_singleton() -> dict[str, Any]:
    """After (alternative): proper lock-based lazy init."""
    global _locked_singleton
    if _locked_singleton is None:
        with _singleton_lock:
            if _locked_singleton is None:
                _locked_singleton = {"initialized": True}
    return _locked_singleton  # type: ignore[return-value]


def pattern3_verify() -> tuple[bool, bool]:
    """Return (bad_ok, good_ok) — good should always be True."""
    results_bad: list[bool] = []
    results_good: list[bool] = []

    def check_bad() -> None:
        results_bad.append(_get_bad_singleton().get("initialized") is True)

    def check_good() -> None:
        results_good.append(_get_good_singleton().get("initialized") is True)

    threads = [threading.Thread(target=check_bad) for _ in range(20)]
    threads += [threading.Thread(target=check_good) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return all(results_bad), all(results_good)


# ---------------------------------------------------------------------------
# Pattern 4: unprotected list accumulator → queue.Queue
# ---------------------------------------------------------------------------


def _bad_accumulator(results: list[int], value: int) -> None:
    """Before: concurrent list.append — not atomic under free-threading."""
    results.append(value)  # may corrupt internal list structure


def _good_accumulator(q: queue.Queue[int], value: int) -> None:
    """After: queue.Queue is thread-safe by design."""
    q.put(value)


def pattern4_before() -> int:
    """Collect values via concurrent list.append."""
    results: list[int] = []
    threads = [
        threading.Thread(target=_bad_accumulator, args=(results, i))
        for i in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(results)


def pattern4_after() -> int:
    """Collect values via concurrent queue.Queue.put."""
    q: queue.Queue[int] = queue.Queue()
    threads = [
        threading.Thread(target=_good_accumulator, args=(q, i))
        for i in range(_N_THREADS * _N_OPS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return q.qsize()


# ---------------------------------------------------------------------------
# Pattern 5: read-modify-write cache → CAS loop
# ---------------------------------------------------------------------------


def _bad_cache_update(cache: dict[str, int], key: str) -> None:
    """Before: unprotected read-modify-write — classic race."""
    current = cache.get(key, 0)
    time.sleep(0)  # simulate real work between read and write
    cache[key] = current + 1


def _good_cache_update(counter: AtomicCounter) -> None:
    """After: AtomicCounter.increment handles the CAS loop internally."""
    counter.increment()


def pattern5_before() -> int:
    """Update a shared cache key from multiple threads."""
    cache: dict[str, int] = {"hits": 0}
    threads = [
        threading.Thread(target=_bad_cache_update, args=(cache, "hits"))
        for _ in range(_N_THREADS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return cache["hits"]


def pattern5_after() -> int:
    """Update an AtomicCounter from multiple threads."""
    counter = AtomicCounter(0)
    threads = [
        threading.Thread(target=_good_cache_update, args=(counter,))
        for _ in range(_N_THREADS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter.get()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _print_pattern(n: int, title: str, before: str, after: str, note: str = "") -> None:
    print(f"\nPattern {n}: {title}")
    print(_SUB)
    print(f"  BEFORE: {before}")
    print(f"  AFTER:  {after}")
    if note:
        print(f"  NOTE:   {note}")


def main() -> None:
    """Run all five migration patterns and print results."""
    expected = _N_THREADS * _N_OPS

    print(_SEP)
    print("  Python 3.14 Free-Threading — Migration Guide (runnable)")
    print(_SEP)

    # -- Pattern 1 --
    _print_pattern(
        1,
        "Global counter: `x += 1` → AtomicCounter.increment()",
        "global_var += 1  # 3 bytecodes, NOT atomic",
        "AtomicCounter.increment()  # serialized with Lock",
    )
    b1 = pattern1_before()
    a1 = pattern1_after()
    lost = expected - b1
    print(
        f"  Before result: {b1:,} (lost {lost:,} updates{'!' if lost > 0 else ' — lucky run'})"
    )
    print(f"  After  result: {a1:,} ({'correct' if a1 == expected else 'ERROR'})")

    # -- Pattern 2 --
    _print_pattern(
        2,
        "Shared dict: naked assignment → SharedState",
        "shared_dict[key] = value  # may drop entries",
        "SharedState.set(key, value)  # RLock protected",
    )
    b2 = pattern2_before()
    a2 = pattern2_after()
    print(
        f"  Before entries: {b2:,} / {expected:,} "
        f"({'OK' if b2 == expected else f'missing {expected - b2:,}'})"
    )
    print(
        f"  After  entries: {a2:,} / {expected:,} ({'correct' if a2 == expected else 'ERROR'})"
    )

    # -- Pattern 3 --
    _print_pattern(
        3,
        "Lazy singleton: DCL → module-level init",
        "if obj is None: if obj is None: obj = ...  # broken DCL",
        "obj = {...}  # module-level — import lock guarantees safety",
        "Alternative: wrap with threading.Lock for explicit lazy init",
    )
    bad_ok, good_ok = pattern3_verify()
    print(f"  Before (DCL)   all threads got valid object: {bad_ok}")
    print(f"  After  (safe)  all threads got valid object: {good_ok}")

    # -- Pattern 4 --
    _print_pattern(
        4,
        "List accumulator: list.append → queue.Queue.put",
        "results.append(value)  # internal list may corrupt",
        "q.put(value)  # queue.Queue is thread-safe",
    )
    b4 = pattern4_before()
    a4 = pattern4_after()
    print(
        f"  Before count: {b4:,} / {expected:,} "
        f"({'OK' if b4 == expected else f'lost {expected - b4:,}'})"
    )
    print(
        f"  After  count: {a4:,} / {expected:,} ({'correct' if a4 == expected else 'ERROR'})"
    )

    # -- Pattern 5 --
    _print_pattern(
        5,
        "Cache update: read-modify-write → AtomicCounter",
        "cache[k] = cache.get(k, 0) + 1  # racy between read & write",
        "AtomicCounter.increment()  # atomic increment",
    )
    b5 = pattern5_before()
    a5 = pattern5_after()
    print(
        f"  Before hits: {b5} / {_N_THREADS} "
        f"({'correct' if b5 == _N_THREADS else f'lost {_N_THREADS - b5}'})"
    )
    print(
        f"  After  hits: {a5} / {_N_THREADS} ({'correct' if a5 == _N_THREADS else 'ERROR'})"
    )

    print(f"\n{_SEP}")
    print("Migration guide complete. Fix every BEFORE pattern before removing the GIL.")
    print(_SEP)


if __name__ == "__main__":
    main()
