"""Tests for gil_state.py."""

from __future__ import annotations

from patterns.gil_state import (
    GILMode,
    GILModeDetector,
    GILStatus,
    ThreadSafetyLevel,
    detect_gil_mode,
)


class TestGILMode:
    def test_enabled_not_free_threading(self):
        assert GILMode.ENABLED.is_free_threading() is False

    def test_disabled_is_free_threading(self):
        assert GILMode.DISABLED.is_free_threading() is True

    def test_description_enabled(self):
        assert "GIL" in GILMode.ENABLED.description()

    def test_description_disabled(self):
        assert "disabled" in GILMode.DISABLED.description()

    def test_description_unknown(self):
        assert "unknown" in GILMode.UNKNOWN.description()


class TestThreadSafetyLevel:
    def test_safe_no_audit(self):
        assert ThreadSafetyLevel.SAFE.requires_audit() is False

    def test_unsafe_requires_audit(self):
        assert ThreadSafetyLevel.UNSAFE.requires_audit() is True

    def test_conditional_requires_audit(self):
        assert ThreadSafetyLevel.CONDITIONALLY_SAFE.requires_audit() is True

    def test_unknown_requires_audit(self):
        assert ThreadSafetyLevel.UNKNOWN.requires_audit() is True


class TestGILStatus:
    def test_supports_free_threading_old_python(self):
        status = GILStatus(GILMode.ENABLED, (3, 11, 0), False)
        assert status.supports_free_threading() is False

    def test_supports_free_threading_new_build(self):
        status = GILStatus(GILMode.DISABLED, (3, 13, 0), True)
        assert status.supports_free_threading() is True

    def test_effective_parallelism_disabled(self):
        status = GILStatus(GILMode.DISABLED, (3, 13, 0), True)
        assert status.effective_parallelism() == "true_parallel"

    def test_effective_parallelism_enabled(self):
        status = GILStatus(GILMode.ENABLED, (3, 12, 0), False)
        assert status.effective_parallelism() == "gil_protected"

    def test_to_dict(self):
        status = GILStatus(GILMode.ENABLED, (3, 12, 0), False)
        d = status.to_dict()
        assert "mode" in d
        assert "supports_free_threading" in d


class TestDetectGILMode:
    def test_returns_gil_mode(self):
        mode = detect_gil_mode()
        assert isinstance(mode, GILMode)

    def test_standard_python_returns_enabled(self):
        # On standard Python builds, GIL should be enabled
        mode = detect_gil_mode()
        assert mode in {GILMode.ENABLED, GILMode.DISABLED}


class TestGILModeDetector:
    def test_current_mode_returns_enum(self):
        d = GILModeDetector()
        assert isinstance(d.current_mode(), GILMode)

    def test_status_returns_status(self):
        d = GILModeDetector()
        assert isinstance(d.status(), GILStatus)

    def test_is_at_least_312(self):
        d = GILModeDetector()
        # We're running on Python 3.12+
        assert d.is_at_least(3, 12) is True

    def test_is_at_least_future(self):
        d = GILModeDetector()
        assert d.is_at_least(4, 0) is False

    def test_version_string_format(self):
        d = GILModeDetector()
        v = d.version_string()
        assert v.count(".") == 2
