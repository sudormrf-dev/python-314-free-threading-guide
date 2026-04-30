"""Threading performance benchmark for Python 3.14 free-threading patterns.

Measures:
  1. AtomicCounter throughput at 1 / 2 / 4 / 8 / 16 threads
  2. SharedState read/write throughput under concurrent load
  3. LockStrategy.NONE vs MUTEX vs RW_LOCK speed comparison

All measurements use only threading and time.perf_counter (stdlib).
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patterns.thread_safety import AtomicCounter, LockStrategy, SharedState

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_WARMUP_OPS = 5_000       # ops before timing starts (cache warm-up)
_BENCH_OPS = 50_000       # ops per thread during measurement
_THREAD_COUNTS = (1, 2, 4, 8, 16)
_SHARED_STATE_KEYS = 8    # number of keys shared across threads


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BenchResult:
    """Single benchmark result row."""

    label: str
    threads: int
    ops_total: int
    elapsed_sec: float

    @property
    def throughput(self) -> float:
        """Operations per second."""
        return self.ops_total / self.elapsed_sec if self.elapsed_sec > 0 else 0.0

    @property
    def latency_us(self) -> float:
        """Average latency per operation in microseconds."""
        return (self.elapsed_sec / self.ops_total) * 1_000_000 if self.ops_total > 0 else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_threads(target: Any, n_threads: int, *args: Any) -> float:
    """Run target in n_threads threads; return wall-clock seconds."""
    barrier = threading.Barrier(n_threads)

    def worker() -> None:
        barrier.wait()  # all threads start simultaneously
        target(*args)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.perf_counter() - t0


def _fmt_throughput(ops: float) -> str:
    if ops >= 1_000_000:
        return f"{ops / 1_000_000:.2f}M ops/s"
    if ops >= 1_000:
        return f"{ops / 1_000:.1f}K ops/s"
    return f"{ops:.0f} ops/s"


def _speedup(base: float, current: float) -> str:
    if base == 0:
        return "N/A"
    ratio = current / base
    return f"{ratio:.2f}x"


# ---------------------------------------------------------------------------
# Benchmark 1: AtomicCounter throughput vs thread count
# ---------------------------------------------------------------------------


def _counter_worker(counter: AtomicCounter, ops: int) -> None:
    for _ in range(ops):
        counter.increment()


def bench_atomic_counter() -> list[BenchResult]:
    """Measure AtomicCounter.increment throughput across thread counts."""
    results: list[BenchResult] = []

    for n in _THREAD_COUNTS:
        # warm up
        warmup = AtomicCounter(0)
        _run_threads(_counter_worker, n, warmup, _WARMUP_OPS)

        counter = AtomicCounter(0)
        elapsed = _run_threads(_counter_worker, n, counter, _BENCH_OPS)
        total_ops = n * _BENCH_OPS
        results.append(BenchResult(
            label="AtomicCounter.increment",
            threads=n,
            ops_total=total_ops,
            elapsed_sec=elapsed,
        ))

    return results


# ---------------------------------------------------------------------------
# Benchmark 2: SharedState read/write throughput
# ---------------------------------------------------------------------------


def _shared_state_writer(state: SharedState, ops: int) -> None:
    keys = [f"k{i}" for i in range(_SHARED_STATE_KEYS)]
    for i in range(ops):
        state.set(keys[i % _SHARED_STATE_KEYS], i)


def _shared_state_reader(state: SharedState, ops: int) -> None:
    keys = [f"k{i}" for i in range(_SHARED_STATE_KEYS)]
    for i in range(ops):
        state.get(keys[i % _SHARED_STATE_KEYS])


def _mixed_worker(state: SharedState, ops: int, write_ratio: float) -> None:
    """Mixed read/write worker at given write_ratio (0.0–1.0)."""
    keys = [f"k{i}" for i in range(_SHARED_STATE_KEYS)]
    write_every = max(1, int(1 / write_ratio)) if write_ratio > 0 else 0
    for i in range(ops):
        key = keys[i % _SHARED_STATE_KEYS]
        if write_every and i % write_every == 0:
            state.set(key, i)
        else:
            state.get(key)


def bench_shared_state() -> list[BenchResult]:
    """Measure SharedState throughput: pure-read, pure-write, 80/20 mixed."""
    results: list[BenchResult] = []
    scenarios = [
        ("SharedState pure-read",  0.0),
        ("SharedState 80/20 mix",  0.2),
        ("SharedState pure-write", 1.0),
    ]

    for label, write_ratio in scenarios:
        for n in _THREAD_COUNTS:
            state = SharedState(strategy=LockStrategy.MUTEX)
            for k in range(_SHARED_STATE_KEYS):
                state.set(f"k{k}", 0)

            # warm up
            _run_threads(_mixed_worker, n, state, _WARMUP_OPS, write_ratio)

            elapsed = _run_threads(_mixed_worker, n, state, _BENCH_OPS, write_ratio)
            total_ops = n * _BENCH_OPS
            results.append(BenchResult(
                label=label,
                threads=n,
                ops_total=total_ops,
                elapsed_sec=elapsed,
            ))

    return results


# ---------------------------------------------------------------------------
# Benchmark 3: LockStrategy comparison
# ---------------------------------------------------------------------------


def _strategy_worker(state: SharedState, ops: int, write_ratio: float) -> None:
    keys = [f"k{i}" for i in range(_SHARED_STATE_KEYS)]
    write_every = max(1, int(1 / write_ratio)) if write_ratio > 0 else 0
    for i in range(ops):
        key = keys[i % _SHARED_STATE_KEYS]
        if write_every and i % write_every == 0:
            state.set(key, i)
        else:
            state.get(key)


def bench_lock_strategies(n_threads: int = 4) -> list[BenchResult]:
    """Compare NONE / MUTEX / RW_LOCK at a fixed thread count (80/20 mix)."""
    results: list[BenchResult] = []
    write_ratio = 0.2

    for strategy in (LockStrategy.NONE, LockStrategy.MUTEX, LockStrategy.RW_LOCK):
        state = SharedState(strategy=strategy)
        for k in range(_SHARED_STATE_KEYS):
            state.set(f"k{k}", 0)

        # warm up
        _run_threads(_strategy_worker, n_threads, state, _WARMUP_OPS, write_ratio)

        elapsed = _run_threads(_strategy_worker, n_threads, state, _BENCH_OPS, write_ratio)
        total_ops = n_threads * _BENCH_OPS
        results.append(BenchResult(
            label=f"LockStrategy.{strategy.name}",
            threads=n_threads,
            ops_total=total_ops,
            elapsed_sec=elapsed,
        ))

    return results


# ---------------------------------------------------------------------------
# Report printers
# ---------------------------------------------------------------------------


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")
    print(f"  {'Threads':>8}  {'Throughput':>14}  {'Latency':>12}  {'Speedup vs 1T':>14}")
    print(f"  {'-' * 56}")


def _print_results(results: list[BenchResult], group_key: str = "label") -> None:
    # Group by label
    groups: dict[str, list[BenchResult]] = {}
    for r in results:
        groups.setdefault(r.label, []).append(r)

    for label, rows in groups.items():
        if len(groups) > 1:
            print(f"\n  [{label}]")
        baseline = rows[0].throughput if rows else 1.0
        for r in rows:
            sp = _speedup(baseline, r.throughput)
            print(f"  {r.threads:>8}  {_fmt_throughput(r.throughput):>14}  "
                  f"{r.latency_us:>9.2f} µs  {sp:>14}")


def _print_strategy_table(results: list[BenchResult]) -> None:
    print(f"\n{'=' * 70}")
    print(f"  LockStrategy comparison  ({results[0].threads} threads, 80/20 read/write)")
    print(f"{'=' * 70}")
    print(f"  {'Strategy':30}  {'Throughput':>14}  {'Latency':>12}  {'vs NONE':>10}")
    print(f"  {'-' * 60}")

    baseline = results[0].throughput if results else 1.0
    for r in results:
        sp = _speedup(baseline, r.throughput)
        print(f"  {r.label:<30}  {_fmt_throughput(r.throughput):>14}  "
              f"{r.latency_us:>9.2f} µs  {sp:>10}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all benchmarks and print a formatted report."""
    print("\n" + "=" * 70)
    print("  Python 3.14 Free-Threading — Performance Benchmarks")
    print(f"  {_BENCH_OPS:,} ops/thread  |  threads: {list(_THREAD_COUNTS)}")
    print("=" * 70)

    # --- Benchmark 1: AtomicCounter ---
    print("\nRunning Benchmark 1: AtomicCounter throughput ...")
    counter_results = bench_atomic_counter()
    _print_header("Benchmark 1 — AtomicCounter.increment() throughput")
    _print_results(counter_results)

    # --- Benchmark 2: SharedState ---
    print("\nRunning Benchmark 2: SharedState read/write throughput ...")
    state_results = bench_shared_state()
    _print_header("Benchmark 2 — SharedState throughput (per scenario)")
    _print_results(state_results)

    # --- Benchmark 3: LockStrategy ---
    print("\nRunning Benchmark 3: LockStrategy comparison ...")
    strategy_results = bench_lock_strategies(n_threads=4)
    _print_strategy_table(strategy_results)

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print("  Summary")
    print(f"{'=' * 70}")

    ctr_1t = next((r for r in counter_results if r.threads == 1), None)
    ctr_8t = next((r for r in counter_results if r.threads == 8), None)
    if ctr_1t and ctr_8t:
        ratio = ctr_8t.throughput / ctr_1t.throughput if ctr_1t.throughput > 0 else 0
        print(f"  AtomicCounter 1T→8T scaling: {ratio:.2f}x "
              f"({'good' if ratio >= 1.5 else 'expected: lock contention limits scaling'})")

    none_r = next((r for r in strategy_results if r.label.endswith("NONE")), None)
    mutex_r = next((r for r in strategy_results if r.label.endswith("MUTEX")), None)
    if none_r and mutex_r:
        overhead = (none_r.throughput - mutex_r.throughput) / none_r.throughput * 100
        print(f"  Lock overhead (NONE vs MUTEX): ~{overhead:.1f}% throughput cost")

    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
