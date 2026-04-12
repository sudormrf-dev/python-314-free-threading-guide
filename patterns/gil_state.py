"""GIL state detection and mode modeling for Python 3.13/3.14 free-threading."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GILMode(str, Enum):
    """GIL operational modes in Python 3.13+."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    UNKNOWN = "unknown"

    def is_free_threading(self) -> bool:
        return self == GILMode.DISABLED

    def description(self) -> str:
        if self == GILMode.ENABLED:
            return "GIL active — single-threaded execution for Python objects"
        if self == GILMode.DISABLED:
            return "GIL disabled — true parallel Python execution (experimental)"
        return "GIL state unknown"


class ThreadSafetyLevel(str, Enum):
    """Safety classification for code under free-threading."""

    SAFE = "safe"
    CONDITIONALLY_SAFE = "conditionally_safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"

    def requires_audit(self) -> bool:
        return self in {
            ThreadSafetyLevel.CONDITIONALLY_SAFE,
            ThreadSafetyLevel.UNSAFE,
            ThreadSafetyLevel.UNKNOWN,
        }


@dataclass
class GILStatus:
    """Runtime GIL status snapshot."""

    mode: GILMode
    python_version: tuple[int, int, int]
    free_threading_build: bool
    gil_ref_count: int = 0

    def supports_free_threading(self) -> bool:
        major, minor, _ = self.python_version
        return (major, minor) >= (3, 13) and self.free_threading_build

    def effective_parallelism(self) -> str:
        if self.mode == GILMode.DISABLED:
            return "true_parallel"
        if self.mode == GILMode.ENABLED:
            return "gil_protected"
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "python_version": list(self.python_version),
            "free_threading_build": self.free_threading_build,
            "supports_free_threading": self.supports_free_threading(),
            "effective_parallelism": self.effective_parallelism(),
        }


def detect_gil_mode() -> GILMode:
    """Detect current GIL mode from sys flags (Python 3.13+)."""
    # sys.flags.gil is available in Python 3.13+ free-threading builds
    # 0 = GIL disabled, 1 = GIL enabled, attribute absent = old Python
    gil_flag = getattr(sys.flags, "gil", None)
    if gil_flag is None:
        return GILMode.ENABLED  # pre-3.13: GIL always on
    return GILMode.DISABLED if gil_flag == 0 else GILMode.ENABLED


class GILModeDetector:
    """Detects and reports GIL mode with version compatibility."""

    def __init__(self) -> None:
        self._version = sys.version_info[:3]

    def current_mode(self) -> GILMode:
        return detect_gil_mode()

    def status(self) -> GILStatus:
        mode = self.current_mode()
        free_threading = getattr(sys.flags, "gil", None) is not None
        return GILStatus(
            mode=mode,
            python_version=self._version,
            free_threading_build=free_threading,
        )

    def is_at_least(self, major: int, minor: int) -> bool:
        return self._version[:2] >= (major, minor)

    def version_string(self) -> str:
        return f"{self._version[0]}.{self._version[1]}.{self._version[2]}"
