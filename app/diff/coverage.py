"""Be explicit about what was reviewed and what was not, and why."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.diff.models import FileDiff


@dataclass(slots=True)
class Limits:
    max_files: int = 100
    max_changed_lines: int = 1500


@dataclass(frozen=True, slots=True)
class SkippedFile:
    path: str
    reason: str


@dataclass(slots=True)
class Coverage:
    reviewed: list[str] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)

    def skipped_by_reason(self) -> dict[str, int]:
        return dict(Counter(s.reason for s in self.skipped))


def skip_reason(fd: FileDiff) -> str | None:
    if fd.ignore_reason:
        return fd.ignore_reason
    if fd.is_truncated:
        return "diff too large for GitHub to return"
    if fd.parse_error:
        return f"could not parse ({fd.parse_error})"
    if not fd.hunks:
        return "no textual changes"
    return None


def apply_limits(files: list[FileDiff], limits: Limits) -> tuple[list[FileDiff], Coverage]:
    """Split files into those we will review and a coverage report for the rest."""
    coverage = Coverage()
    reviewed: list[FileDiff] = []
    total_changed = 0
    for fd in files:
        reason = skip_reason(fd)
        if reason is None and len(reviewed) >= limits.max_files:
            reason = "over file cap"
        elif reason is None and total_changed + fd.changed_lines > limits.max_changed_lines:
            reason = "over changed-lines cap"
        if reason:
            coverage.skipped.append(SkippedFile(fd.path, reason))
            continue
        reviewed.append(fd)
        coverage.reviewed.append(fd.path)
        total_changed += fd.changed_lines
    return reviewed, coverage
