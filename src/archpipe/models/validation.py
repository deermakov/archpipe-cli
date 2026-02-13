"""Validation result models used across parser and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationLevel(str, Enum):
    """Issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(slots=True)
class ValidationLocation:
    """Location information for an issue."""

    file: str
    line: int | None = None
    block: str | None = None


@dataclass(slots=True)
class ValidationIssue:
    """Single validation issue."""

    level: ValidationLevel
    code: str
    message: str
    location: ValidationLocation
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize issue to dictionary."""
        payload: dict[str, Any] = {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
            "location": {
                "file": self.location.file,
                "line": self.location.line,
                "block": self.location.block,
            },
        }
        if self.suggestion:
            payload["suggestion"] = self.suggestion
        return payload


@dataclass(slots=True)
class ValidationReport:
    """Validation report with aggregate data."""

    hld_file: str
    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Errors only."""
        return [issue for issue in self.issues if issue.level == ValidationLevel.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Warnings only."""
        return [
            issue
            for issue in self.issues
            if issue.level == ValidationLevel.WARNING
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to dictionary."""
        return {
            "hld_file": self.hld_file,
            "metrics": self.metrics,
            "issues": [issue.to_dict() for issue in self.issues],
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }

    def add_issue(self, issue: ValidationIssue) -> None:
        """Append issue to report."""
        self.issues.append(issue)

    def has_errors(self) -> bool:
        """Check if report contains errors."""
        return bool(self.errors)
