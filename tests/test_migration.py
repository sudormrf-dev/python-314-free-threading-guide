"""Tests for migration.py."""

from __future__ import annotations

from patterns.migration import (
    CompatLayer,
    MigrationChecker,
    MigrationIssue,
    MigrationReport,
    MigrationSeverity,
)


class TestMigrationSeverity:
    def test_critical_is_blocking(self):
        assert MigrationSeverity.CRITICAL.is_blocking() is True

    def test_info_not_blocking(self):
        assert MigrationSeverity.INFO.is_blocking() is False

    def test_priority_order(self):
        assert (
            MigrationSeverity.CRITICAL.priority() > MigrationSeverity.WARNING.priority()
        )


class TestMigrationIssue:
    def test_blocking_error(self):
        issue = MigrationIssue("FT001", "test", MigrationSeverity.ERROR)
        assert issue.is_blocking() is True

    def test_not_blocking_warning(self):
        issue = MigrationIssue("FT003", "test", MigrationSeverity.WARNING)
        assert issue.is_blocking() is False

    def test_to_dict(self):
        issue = MigrationIssue("FT001", "Global dict", MigrationSeverity.CRITICAL)
        d = issue.to_dict()
        assert d["code"] == "FT001"
        assert d["blocking"] is True


class TestMigrationReport:
    def test_empty_is_ready(self):
        r = MigrationReport("proj")
        assert r.is_ready() is True

    def test_blocking_issue_not_ready(self):
        r = MigrationReport("proj")
        r.add_issue(MigrationIssue("FT001", "bad", MigrationSeverity.CRITICAL))
        assert r.is_ready() is False

    def test_add_issue_returns_self(self):
        r = MigrationReport("proj")
        issue = MigrationIssue("FT001", "t", MigrationSeverity.INFO)
        assert r.add_issue(issue) is r

    def test_by_severity(self):
        r = MigrationReport("proj")
        r.add_issue(MigrationIssue("A", "a", MigrationSeverity.INFO))
        r.add_issue(MigrationIssue("B", "b", MigrationSeverity.ERROR))
        assert len(r.by_severity(MigrationSeverity.INFO)) == 1

    def test_severity_counts(self):
        r = MigrationReport("proj")
        r.add_issue(MigrationIssue("A", "a", MigrationSeverity.WARNING))
        r.add_issue(MigrationIssue("B", "b", MigrationSeverity.WARNING))
        counts = r.severity_counts()
        assert counts["warning"] == 2

    def test_top_issues_sorted(self):
        r = MigrationReport("proj")
        r.add_issue(MigrationIssue("A", "info", MigrationSeverity.INFO))
        r.add_issue(MigrationIssue("B", "crit", MigrationSeverity.CRITICAL))
        top = r.top_issues(1)
        assert top[0].severity == MigrationSeverity.CRITICAL

    def test_to_dict(self):
        r = MigrationReport("myproject", checked_files=10)
        d = r.to_dict()
        assert d["project"] == "myproject"
        assert d["checked_files"] == 10


class TestCompatLayer:
    def test_not_deprecated(self):
        cl = CompatLayer("lock", "GIL", "threading.Lock")
        assert cl.is_deprecated() is False

    def test_deprecated(self):
        cl = CompatLayer("old", "GIL", "Lock", deprecated_in="3.14")
        assert cl.is_deprecated() is True

    def test_migration_summary(self):
        cl = CompatLayer("x", "GIL", "Lock")
        s = cl.migration_summary()
        assert "GIL" in s
        assert "Lock" in s


class TestMigrationChecker:
    def test_known_issue_count(self):
        c = MigrationChecker()
        assert c.known_issue_count() > 0

    def test_all_known_codes(self):
        c = MigrationChecker()
        codes = c.all_known_codes()
        assert "FT001" in codes

    def test_check_returns_report(self):
        c = MigrationChecker()
        r = c.check("myproject", [])
        assert isinstance(r, MigrationReport)

    def test_add_extra_issue(self):
        c = MigrationChecker()
        c.add_issue(MigrationIssue("CUSTOM", "custom", MigrationSeverity.WARNING))
        r = c.check("proj", [])
        codes = [i.code for i in r.issues]
        assert "CUSTOM" in codes

    def test_report_has_blocking(self):
        c = MigrationChecker()
        r = c.check("proj", [])
        assert len(r.blocking_issues()) > 0
