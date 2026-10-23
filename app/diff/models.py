"""Typed representation of a pull request diff.

Parsing produces these objects once; line mapping, rule checks, prompt rendering
and evaluation all work from them instead of re-parsing text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LineKind = Literal["add", "del", "ctx"]


@dataclass(frozen=True, slots=True)
class DiffLine:
    kind: LineKind
    text: str
    old_no: int | None  # line number in the base file (None for added lines)
    new_no: int | None  # line number in the head file (None for deleted lines)


@dataclass(slots=True)
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    section: str = ""
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def old_count(self) -> int:
        return sum(1 for ln in self.lines if ln.kind in ("ctx", "del"))

    @property
    def new_count(self) -> int:
        return sum(1 for ln in self.lines if ln.kind in ("ctx", "add"))

    @property
    def new_range(self) -> tuple[int, int] | None:
        """First and last head-file line this hunk actually contains, or None."""
        nos = [ln.new_no for ln in self.lines if ln.new_no is not None]
        return (min(nos), max(nos)) if nos else None


@dataclass(slots=True)
class FileDiff:
    path: str
    status: str = "modified"  # added | removed | modified | renamed | copied | unchanged
    old_path: str | None = None
    language: str | None = None
    hunks: list[Hunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    is_binary: bool = False
    is_truncated: bool = False  # GitHub returned no patch although the file changed
    ignore_reason: str | None = None
    parse_error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ignored(self) -> bool:
        return self.ignore_reason is not None

    @property
    def reviewable(self) -> bool:
        return (
            self.ignore_reason is None
            and not self.is_truncated
            and self.parse_error is None
            and bool(self.hunks)
        )

    @property
    def changed_lines(self) -> int:
        return self.additions + self.deletions

    def added_lines(self) -> list[DiffLine]:
        return [ln for h in self.hunks for ln in h.lines if ln.kind == "add"]
