"""Threading demo: AtomicCounter and SharedState under concurrent load.

Demonstrates:
- AtomicCounter with 10+ threads (safe vs unsafe increment)
- SharedState read/write under concurrency
- Race condition simulation and fix
- Clear before/after output for each scenario
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

# Allow running from repo root or examples/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patterns.thread_safety import AtomicCounter, LockStrategy, SharedState

_SEPARATOR = "-" * 60
_NUM_THREADS = 12
_INCREMENTS_PER_THREAD = 500


# ---------------------------------------------------------------------------
# Scenario 1: Safe counter vs unsafe counter
# ---------------------------------------------------------------------------


def _safe_worker(counter: AtomicCounter, n: int) -> None:
    """Increment an AtomicCounter n times — fully thread-safe."""
    for _ in range(n):
        counter.increment()


def _unsafe_worker(shared: list[int], n: int) -> None:
    """Increment a plain list element n times — NOT thread-safe."""
    for _ in range(n):
        # read-modify-write is not atomic without a lock
        shared[0] = shared[0] + 1


def demo_atomic_counter() -> None:
    """Show AtomicCounter correctness vs plain list under 12 threads."""
    print(_SEPARATOR)
    print("SCENARIO 1 — AtomicCounter: safe vs unsafe")
    print(_SEPARATOR)

    expected = _NUM_THREADS * _INCREMENTS_PER_THREAD

    # --- SAFE ---
    safe_counter = AtomicCounter(0)
    threads = [
        threading.Thread(target=_safe_worker, args=(safe_counter, _INCREMENTS_PER_THREAD))
        for _ in range(_NUM_THREADS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    safe_result = safe_counter.get()
    print(f"  [SAFE]   Expected={expected:,}  Got={safe_result:,}  "
          f"{'OK' if safe_result == expected else 'CORRUPTED'}")

    # --- UNSAFE ---
    unsafe_shared: list[int] = [0]
    threads = [
        threading.Thread(target=_unsafe_worker, args=(unsafe_shared, _INCREMENTS_PER_THREAD))
        for _ in range(_NUM_THREADS)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unsafe_result = unsafe_shared[0]
    lost = expected - unsafe_result
    marker = "OK (lucky)" if unsafe_result == expected else f"LOST {lost:,} increments"
    print(f"  [UNSAFE] Expected={expected:,}  Got={unsafe_result:,}  {marker}")
    print()


# ---------------------------------------------------------------------------
# Scenario 2: SharedState concurrent read/write
# ---------------------------------------------------------------------------


def _writer(state: SharedState, key: str, values: list[int]) -> None:
    """Write sequential values into SharedState under a given key."""
    for v in values:
        state.set(key, v)
        time.sleep(0)  # yield to other threads


def _reader(state: SharedState, key: str, results: list[int | None], idx: int) -> None:
    """Read a value from SharedState and record it."""
    time.sleep(0)  # let writers start
    results[idx] = state.get(key)


def demo_shared_state() -> None:
    """Demonstrate SharedState under concurrent readers and writers."""
    print(_SEPARATOR)
    print("SCENARIO 2 — SharedState: concurrent readers + writers")
    print(_SEPARATOR)

    state = SharedState(strategy=LockStrategy.MUTEX)
    state.set("counter", 0)

    read_results: list[int | None] = [None] * 8
    readers = [
        threading.Thread(target=_reader, args=(state, "counter", read_results, i))
        for i in range(8)
    ]
    writers = [
        threading.Thread(target=_writer, args=(state, "counter", list(range(50))))
        for _ in range(4)
    ]

    for t in writers + readers:
        t.start()
    for t in writers + readers:
        t.join()

    valid = [r for r in read_results if r is not None]
    print(f"  Readers saw values: {valid}")
    print(f"  Final value in state: {state.get('counter')}")
    print(f"  State version: {state.version()}  (incremented on each write)")
    print()


# ---------------------------------------------------------------------------
# Scenario 3: Race condition simulation and fix
# ---------------------------------------------------------------------------

_race_total = 0
_race_lock = threading.Lock()


def _unsafe_increment(n: int) -> None:
    """Increment module-level counter without any protection."""
    global _race_total  # noqa: PLW0603
    for _ in range(n):
        _race_total += 1  # read-modify-write: NOT atomic


def _safe_increment(counter: AtomicCounter, n: int) -> None:
    """Increment AtomicCounter — protected by internal lock."""
    for _ in range(n):
        counter.increment()


def demo_race_condition() -> None:
    """Show a real race condition and its fix side by side."""
    print(_SEPARATOR)
    print("SCENARIO 3 — Race condition: broken global vs AtomicCounter fix")
    print(_SEPARATOR)

    n_threads = 10
    n_ops = 1000
    expected = n_threads * n_ops

    # Broken version: unprotected global
    global _race_total  # noqa: PLW0603
    _race_total = 0
    threads = [threading.Thread(target=_unsafe_increment, args=(n_ops,)) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    broken_result = _race_total
    lost = expected - broken_result
    print(f"  [BROKEN] Expected={expected:,}  Got={broken_result:,}  Lost={lost:,} updates")
    print("           Root cause: `x += 1` is 3 bytecodes — not atomic under free-threading")
    print()

    # Fixed version: AtomicCounter
    fixed_counter = AtomicCounter(0)
    threads = [threading.Thread(target=_safe_increment, args=(fixed_counter, n_ops)) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    fixed_result = fixed_counter.get()
    print(f"  [FIXED]  Expected={expected:,}  Got={fixed_result:,}  "
          f"{'OK — no lost updates' if fixed_result == expected else 'UNEXPECTED MISMATCH'}")
    print("           Fix: use AtomicCounter.increment() — internally serialized with Lock")
    print()


# ---------------------------------------------------------------------------
# Scenario 4: compare_and_set (CAS) pattern
# ---------------------------------------------------------------------------


def _cas_worker(counter: AtomicCounter, target: int, results: list[bool], idx: int) -> None:
    """Try to CAS the counter from target to target+1."""
    results[idx] = counter.compare_and_set(target, target + 1)


def demo_compare_and_set() -> None:
    """Demonstrate compare-and-set: only one thread wins the CAS."""
    print(_SEPARATOR)
    print("SCENARIO 4 — compare_and_set: exactly one winner among 10 threads")
    print(_SEPARATOR)

    counter = AtomicCounter(42)
    results: list[bool] = [False] * 10
    threads = [
        threading.Thread(target=_cas_worker, args=(counter, 42, results, i))
        for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    wins = sum(results)
    print(f"  CAS(42 -> 43): {wins} thread(s) succeeded out of 10")
    print(f"  Counter final value: {counter.get()}")
    print(f"  {'Correct — exactly one CAS winner' if wins == 1 else 'WARNING: unexpected result'}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all threading demos."""
    print()
    print("=" * 60)
    print("  Python 3.14 Free-Threading Demo")
    print(f"  {_NUM_THREADS} threads, {_INCREMENTS_PER_THREAD} ops/thread")
    print("=" * 60)
    print()

    demo_atomic_counter()
    demo_shared_state()
    demo_race_condition()
    demo_compare_and_set()

    print(_SEPARATOR)
    print("All demos complete.")
    print(_SEPARATOR)


if __name__ == "__main__":
    main()
