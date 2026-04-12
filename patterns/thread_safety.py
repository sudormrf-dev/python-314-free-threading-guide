"""Thread-safe primitives and patterns for free-threaded Python."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LockStrategy(str, Enum):
    """Locking strategies for shared state."""

    NONE = "none"
    MUTEX = "mutex"
    RW_LOCK = "rw_lock"
    OPTIMISTIC = "optimistic"
    LOCK_FREE = "lock_free"

    def has_write_contention(self) -> bool:
        return self in {LockStrategy.MUTEX, LockStrategy.RW_LOCK}


class AtomicCounter:
    """Thread-safe counter using a lock (models atomic increment pattern)."""

    def __init__(self, initial: int = 0) -> None:
        self._value = initial
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        with self._lock:
            self._value += amount
            return self._value

    def decrement(self, amount: int = 1) -> int:
        with self._lock:
            self._value -= amount
            return self._value

    def get(self) -> int:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    def compare_and_set(self, expected: int, new_value: int) -> bool:
        with self._lock:
            if self._value == expected:
                self._value = new_value
                return True
            return False


class SharedState:
    """Thread-safe shared state container."""

    def __init__(self, strategy: LockStrategy = LockStrategy.MUTEX) -> None:
        self._strategy = strategy
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._version = 0

    @property
    def strategy(self) -> LockStrategy:
        return self._strategy

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._version += 1

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._version += 1
                return True
            return False

    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())


class ThreadSafeQueue:
    """Bounded thread-safe queue with backpressure."""

    def __init__(self, maxsize: int = 0) -> None:
        self._maxsize = maxsize
        self._queue: deque[Any] = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> bool:
        with self._not_full:
            if self._maxsize > 0 and len(self._queue) >= self._maxsize:
                if not block:
                    return False
                self._not_full.wait(timeout)
                if len(self._queue) >= self._maxsize:
                    return False
            self._queue.append(item)
            self._not_empty.notify()
            return True

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        with self._not_empty:
            if not self._queue:
                if not block:
                    return None
                self._not_empty.wait(timeout)
                if not self._queue:
                    return None
            item = self._queue.popleft()
            self._not_full.notify()
            return item

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0

    def is_full(self) -> bool:
        with self._lock:
            return self._maxsize > 0 and len(self._queue) >= self._maxsize


@dataclass
class ThreadSafetyAudit:
    """Audit record for thread safety analysis."""

    module_name: str
    safe_count: int = 0
    unsafe_count: int = 0
    conditional_count: int = 0
    notes: list[str] = field(default_factory=list)

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def total(self) -> int:
        return self.safe_count + self.unsafe_count + self.conditional_count

    def safety_score(self) -> float:
        t = self.total()
        if t == 0:
            return 1.0
        return self.safe_count / t

    def is_safe(self, threshold: float = 0.8) -> bool:
        return self.safety_score() >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module_name,
            "safe": self.safe_count,
            "unsafe": self.unsafe_count,
            "conditional": self.conditional_count,
            "score": self.safety_score(),
        }
