"""Migration guide patterns: GIL → free-threading compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


class MigrationSeverity(str, Enum):
    """Severity of a migration issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def is_blocking(self) -> bool:
        return self in {MigrationSeverity.ERROR, MigrationSeverity.CRITICAL}

    def priority(self) -> int:
        order = {
            MigrationSeverity.INFO: 0,
            MigrationSeverity.WARNING: 1,
            MigrationSeverity.ERROR: 2,
            MigrationSeverity.CRITICAL: 3,
        }
        return order[self]


@dataclass
class MigrationIssue:
    """A single migration concern."""

    code: str
    title: str
    severity: MigrationSeverity
    description: str = ""
    affected_pattern: str = ""
    fix: str = ""
    docs_url: str = ""

    def is_blocking(self) -> bool:
        return self.severity.is_blocking()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity.value,
            "description": self.description,
            "fix": self.fix,
            "blocking": self.is_blocking(),
        }


@dataclass
class MigrationReport:
    """Full migration analysis report."""

    project_name: str
    issues: list[MigrationIssue] = field(default_factory=list)
    checked_files: int = 0
    free_threading_ready: bool = False

    def add_issue(self, issue: MigrationIssue) -> MigrationReport:
        self.issues.append(issue)
        return self

    def blocking_issues(self) -> list[MigrationIssue]:
        return [i for i in self.issues if i.is_blocking()]

    def by_severity(self, severity: MigrationSeverity) -> list[MigrationIssue]:
        return [i for i in self.issues if i.severity == severity]

    def is_ready(self) -> bool:
        return len(self.blocking_issues()) == 0

    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            key = issue.severity.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def top_issues(self, n: int = 5) -> list[MigrationIssue]:
        sorted_issues = sorted(
            self.issues, key=lambda i: i.severity.priority(), reverse=True
        )
        return sorted_issues[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project_name,
            "total_issues": len(self.issues),
            "blocking": len(self.blocking_issues()),
            "checked_files": self.checked_files,
            "ready": self.is_ready(),
            "severity_counts": self.severity_counts(),
        }


@dataclass
class CompatLayer:
    """Compatibility shim description for GIL-dependent code."""

    name: str
    original_pattern: str
    safe_replacement: str
    python_version_min: str = "3.13"
    performance_impact: str = "low"
    notes: str = ""
    deprecated_in: str | None = None

    def is_deprecated(self) -> bool:
        return self.deprecated_in is not None

    def migration_summary(self) -> str:
        return f"{self.original_pattern} → {self.safe_replacement} (Python {self.python_version_min}+)"


class MigrationChecker:
    """Checks code patterns for free-threading compatibility."""

    # Known problematic patterns
    _KNOWN_ISSUES: ClassVar[list[MigrationIssue]] = [
        MigrationIssue(
            code="FT001",
            title="Global dict mutation without lock",
            severity=MigrationSeverity.CRITICAL,
            description="Dict operations are not atomic under free-threading",
            fix="Use threading.Lock or concurrent.futures.thread-local dicts",
        ),
        MigrationIssue(
            code="FT002",
            title="Lazy singleton initialization",
            severity=MigrationSeverity.ERROR,
            description="Double-checked locking is broken without GIL",
            fix="Use threading.local() or module-level initialization",
        ),
        MigrationIssue(
            code="FT003",
            title="Shared list.append in loop",
            severity=MigrationSeverity.WARNING,
            description="list.append is not guaranteed atomic without GIL",
            fix="Use queue.Queue or protect with Lock",
        ),
        MigrationIssue(
            code="FT004",
            title="C extension without Py_TPFLAGS_BASETYPE",
            severity=MigrationSeverity.INFO,
            description="Extensions may need thread-safety audit",
            fix="Add Py_GIL_DISABLED guards or use per-object locks",
        ),
    ]

    def __init__(self) -> None:
        self._extra_issues: list[MigrationIssue] = []

    def add_issue(self, issue: MigrationIssue) -> None:
        self._extra_issues.append(issue)

    def check(self, project_name: str, patterns_found: list[str]) -> MigrationReport:
        report = MigrationReport(project_name=project_name)
        pattern_set = set(patterns_found)
        for issue in self._KNOWN_ISSUES:
            if issue.affected_pattern in pattern_set or not issue.affected_pattern:
                report.add_issue(issue)
        for issue in self._extra_issues:
            report.add_issue(issue)
        report.free_threading_ready = report.is_ready()
        return report

    def all_known_codes(self) -> list[str]:
        return [i.code for i in self._KNOWN_ISSUES]

    def known_issue_count(self) -> int:
        return len(self._KNOWN_ISSUES)
