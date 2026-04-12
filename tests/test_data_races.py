"""Tests for data_races.py."""

from __future__ import annotations

from patterns.data_races import (
    DataRacePattern,
    RaceCondition,
    RaceDetector,
    SafetyAnnotation,
    check_shared_mutation,
)


class TestDataRacePattern:
    def test_unsync_rmw_is_critical(self):
        assert DataRacePattern.UNSYNC_READ_MODIFY_WRITE.is_critical() is True

    def test_lazy_init_not_critical(self):
        assert DataRacePattern.LAZY_INIT.is_critical() is False

    def test_global_state_is_critical(self):
        assert DataRacePattern.GLOBAL_STATE.is_critical() is True


class TestSafetyAnnotation:
    def test_thread_safe_implies_safe(self):
        assert SafetyAnnotation.THREAD_SAFE.implies_safe() is True

    def test_immutable_implies_safe(self):
        assert SafetyAnnotation.IMMUTABLE.implies_safe() is True

    def test_not_thread_safe_does_not_imply(self):
        assert SafetyAnnotation.NOT_THREAD_SAFE.implies_safe() is False

    def test_requires_lock_not_safe(self):
        assert SafetyAnnotation.REQUIRES_LOCK.implies_safe() is False


class TestRaceCondition:
    def test_critical_if_pattern_critical(self):
        rc = RaceCondition(DataRacePattern.GLOBAL_STATE, "global dict modified")
        assert rc.is_critical() is True

    def test_not_critical_if_false_positive(self):
        rc = RaceCondition(DataRacePattern.GLOBAL_STATE, "desc", false_positive=True)
        assert rc.is_critical() is False

    def test_to_dict(self):
        rc = RaceCondition(
            DataRacePattern.LAZY_INIT, "lazy init found", location="mod.py:10"
        )
        d = rc.to_dict()
        assert d["pattern"] == "lazy_init"
        assert d["location"] == "mod.py:10"


class TestCheckSharedMutation:
    def test_shared_mutable_no_lock(self):
        rc = check_shared_mutation(
            "dict", is_mutable=True, has_lock=False, is_shared=True
        )
        assert rc is not None

    def test_locked_no_issue(self):
        rc = check_shared_mutation(
            "dict", is_mutable=True, has_lock=True, is_shared=True
        )
        assert rc is None

    def test_not_shared_no_issue(self):
        rc = check_shared_mutation(
            "list", is_mutable=True, has_lock=False, is_shared=False
        )
        assert rc is None

    def test_immutable_no_issue(self):
        rc = check_shared_mutation(
            "tuple", is_mutable=False, has_lock=False, is_shared=True
        )
        assert rc is None


class TestRaceDetector:
    def setup_method(self):
        self.detector = RaceDetector()

    def test_initial_empty(self):
        assert self.detector.condition_count() == 0

    def test_report_adds_condition(self):
        self.detector.report(RaceCondition(DataRacePattern.LAZY_INIT, "desc"))
        assert self.detector.condition_count() == 1

    def test_critical_conditions(self):
        self.detector.report(RaceCondition(DataRacePattern.GLOBAL_STATE, "critical"))
        self.detector.report(RaceCondition(DataRacePattern.LAZY_INIT, "not critical"))
        assert len(self.detector.critical_conditions()) == 1

    def test_false_positive_count(self):
        self.detector.report(
            RaceCondition(DataRacePattern.LAZY_INIT, "fp", false_positive=True)
        )
        assert self.detector.false_positive_count() == 1

    def test_real_count(self):
        self.detector.report(RaceCondition(DataRacePattern.LAZY_INIT, "real"))
        self.detector.report(
            RaceCondition(DataRacePattern.LAZY_INIT, "fp", false_positive=True)
        )
        assert self.detector.real_count() == 1

    def test_annotate_and_get(self):
        self.detector.annotate("MyClass", SafetyAnnotation.THREAD_SAFE)
        assert self.detector.get_annotation("MyClass") == SafetyAnnotation.THREAD_SAFE

    def test_annotation_missing_returns_none(self):
        assert self.detector.get_annotation("Unknown") is None

    def test_patterns_found(self):
        self.detector.report(RaceCondition(DataRacePattern.GLOBAL_STATE, "g"))
        self.detector.report(
            RaceCondition(DataRacePattern.LAZY_INIT, "fp", false_positive=True)
        )
        patterns = self.detector.patterns_found()
        assert DataRacePattern.GLOBAL_STATE in patterns
        assert DataRacePattern.LAZY_INIT not in patterns  # false positive excluded

    def test_summary(self):
        self.detector.report(RaceCondition(DataRacePattern.GLOBAL_STATE, "g"))
        s = self.detector.summary()
        assert s["total"] == 1
        assert "critical" in s
