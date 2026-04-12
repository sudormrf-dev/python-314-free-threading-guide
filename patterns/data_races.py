"""Data race detection patterns for free-threaded Python."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DataRacePattern(str, Enum):
    """Known data race patterns in Python code."""

    SHARED_MUTABLE_DEFAULT = "shared_mutable_default"
    UNSYNC_READ_MODIFY_WRITE = "unsync_read_modify_write"
    LAZY_INIT = "lazy_init"
    DOUBLE_CHECKED_LOCKING = "double_checked_locking"
    UNSYNC_ITERATOR = "unsync_iterator"
    SINGLETON = "singleton"
    GLOBAL_STATE = "global_state"

    def is_critical(self) -> bool:
        return self in {
            DataRacePattern.UNSYNC_READ_MODIFY_WRITE,
            DataRacePattern.DOUBLE_CHECKED_LOCKING,
            DataRacePattern.GLOBAL_STATE,
        }


class SafetyAnnotation(str, Enum):
    """Thread-safety annotations for code analysis."""

    THREAD_SAFE = "thread_safe"
    NOT_THREAD_SAFE = "not_thread_safe"
    GUARDED_BY = "guarded_by"
    REQUIRES_LOCK = "requires_lock"
    LOCK_FREE = "lock_free"
    IMMUTABLE = "immutable"

    def implies_safe(self) -> bool:
        return self in {
            SafetyAnnotation.THREAD_SAFE,
            SafetyAnnotation.LOCK_FREE,
            SafetyAnnotation.IMMUTABLE,
        }


@dataclass
class RaceCondition:
    """A detected or potential race condition."""

    pattern: DataRacePattern
    description: str
    location: str = ""
    severity: str = "medium"
    fix_suggestion: str = ""
    false_positive: bool = False

    def is_critical(self) -> bool:
        return self.pattern.is_critical() and not self.false_positive

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern.value,
            "description": self.description,
            "location": self.location,
            "severity": self.severity,
            "fix": self.fix_suggestion,
            "false_positive": self.false_positive,
        }


def check_shared_mutation(
    obj_type: str,
    is_mutable: bool,
    has_lock: bool,
    is_shared: bool,
) -> RaceCondition | None:
    """Check if a shared mutable object is a race condition risk."""
    if not is_shared or not is_mutable:
        return None
    if has_lock:
        return None
    return RaceCondition(
        pattern=DataRacePattern.UNSYNC_READ_MODIFY_WRITE,
        description=f"Shared mutable {obj_type} without synchronization",
        severity="high",
        fix_suggestion=f"Protect {obj_type} with a threading.Lock or use thread-local storage",
    )


class RaceDetector:
    """Collects and analyzes race conditions."""

    def __init__(self) -> None:
        self._conditions: list[RaceCondition] = []
        self._annotations: dict[str, SafetyAnnotation] = {}

    def report(self, condition: RaceCondition) -> None:
        self._conditions.append(condition)

    def annotate(self, symbol: str, annotation: SafetyAnnotation) -> None:
        self._annotations[symbol] = annotation

    def get_annotation(self, symbol: str) -> SafetyAnnotation | None:
        return self._annotations.get(symbol)

    def critical_conditions(self) -> list[RaceCondition]:
        return [c for c in self._conditions if c.is_critical()]

    def all_conditions(self) -> list[RaceCondition]:
        return list(self._conditions)

    def condition_count(self) -> int:
        return len(self._conditions)

    def false_positive_count(self) -> int:
        return sum(1 for c in self._conditions if c.false_positive)

    def real_count(self) -> int:
        return sum(1 for c in self._conditions if not c.false_positive)

    def patterns_found(self) -> set[DataRacePattern]:
        return {c.pattern for c in self._conditions if not c.false_positive}

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.condition_count(),
            "critical": len(self.critical_conditions()),
            "false_positives": self.false_positive_count(),
            "real": self.real_count(),
            "patterns": [p.value for p in self.patterns_found()],
        }
