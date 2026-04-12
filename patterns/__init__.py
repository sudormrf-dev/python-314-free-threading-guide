"""Python 3.14 free-threading patterns and migration guide."""

from __future__ import annotations

from patterns.data_races import (
    DataRacePattern,
    RaceCondition,
    RaceDetector,
    SafetyAnnotation,
    check_shared_mutation,
)
from patterns.gil_state import (
    GILMode,
    GILModeDetector,
    GILStatus,
    ThreadSafetyLevel,
    detect_gil_mode,
)
from patterns.migration import (
    CompatLayer,
    MigrationChecker,
    MigrationIssue,
    MigrationReport,
    MigrationSeverity,
)
from patterns.thread_safety import (
    AtomicCounter,
    LockStrategy,
    SharedState,
    ThreadSafeQueue,
    ThreadSafetyAudit,
)

__all__ = [
    "AtomicCounter",
    "CompatLayer",
    "DataRacePattern",
    "GILMode",
    "GILModeDetector",
    "GILStatus",
    "LockStrategy",
    "MigrationChecker",
    "MigrationIssue",
    "MigrationReport",
    "MigrationSeverity",
    "RaceCondition",
    "RaceDetector",
    "SafetyAnnotation",
    "SharedState",
    "ThreadSafeQueue",
    "ThreadSafetyAudit",
    "ThreadSafetyLevel",
    "check_shared_mutation",
    "detect_gil_mode",
]
