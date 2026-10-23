"""Which head-file lines can GitHub attach an inline review comment to?

GitHub only accepts comments on lines that appear in the diff (added or context
lines on the RIGHT side). Anything else returns 422, so we check first.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.diff.models import FileDiff, Hunk


def commentable_lines(fd: FileDiff) -> frozenset[int]:
    return frozenset(
        ln.new_no for h in fd.hunks for ln in h.lines if ln.new_no is not None
    )


def is_commentable(fd: FileDiff, line: int) -> bool:
    return line in commentable_lines(fd)


def hunk_for_line(fd: FileDiff, line: int) -> Hunk | None:
    for h in fd.hunks:
        rng = h.new_range
        if rng and rng[0] <= line <= rng[1]:
            return h
    return None


def nearest_commentable(fd: FileDiff, line: int, max_distance: int = 3) -> int | None:
    valid = commentable_lines(fd)
    if line in valid:
        return line
    candidates = [n for n in valid if abs(n - line) <= max_distance]
    return min(candidates, key=lambda n: (abs(n - line), n)) if candidates else None


def content_hash(hunk: Hunk) -> str:
    """Stable id of a hunk's content (for caching: same hunk, same review)."""
    digest = hashlib.sha256()
    for ln in hunk.lines:
        digest.update(f"{ln.kind}:{ln.text}\n".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Location:
    line: int
    start_line: int | None = None


def resolve_location(fd: FileDiff, start: int, end: int) -> Location | None:
    """Pick a valid comment location for a finding spanning start..end, or None."""
    if start > end:
        start, end = end, start
    valid = commentable_lines(fd)
    if start in valid and end in valid and start < end:
        h_start, h_end = hunk_for_line(fd, start), hunk_for_line(fd, end)
        if h_start is not None and h_start is h_end:
            return Location(line=end, start_line=start)
    if start in valid:
        return Location(line=start)
    near = nearest_commentable(fd, start)
    return Location(line=near) if near is not None else None
