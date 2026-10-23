"""Unified-diff hunk parser.

Design rules:
  * Pure function: text in, typed objects out. No I/O.
  * Never raises on odd input. Problems become warnings; the caller decides.
  * Splits on "\\n" only (like git), so U+2028 etc. inside a line stay in the line,
    and a trailing "\\r" (CRLF files) is stripped.
  * Each side's line counter starts at the header value. For a zero-length side
    (git diff -U0) the header names the line *before* the change, but no line of
    that side exists, so no shift is needed in this representation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.diff.models import DiffLine, Hunk

RE_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: ?(.*))?$")


@dataclass(slots=True)
class ParseResult:
    hunks: list[Hunk] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_patch_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [ln[:-1] if ln.endswith("\r") else ln for ln in lines]


def _check_counts(hunk: Hunk | None, warnings: list[str]) -> None:
    if hunk is None:
        return
    if hunk.old_count != hunk.old_len or hunk.new_count != hunk.new_len:
        warnings.append(
            f"hunk at -{hunk.old_start} +{hunk.new_start}: header says "
            f"({hunk.old_len},{hunk.new_len}) lines, found ({hunk.old_count},{hunk.new_count})"
        )


def parse_patch(patch: str | None) -> ParseResult:
    result = ParseResult()
    if not patch:
        return result

    cur: Hunk | None = None
    skipping = False
    old_no = new_no = 0

    for raw in split_patch_lines(patch):
        if raw.startswith("@@"):
            m = RE_HUNK.match(raw)
            _check_counts(cur, result.warnings)
            if not m:
                result.warnings.append(f"skipped malformed hunk header: {raw[:60]!r}")
                cur, skipping = None, True
                continue
            old_start = int(m.group(1))
            old_len = int(m.group(2)) if m.group(2) is not None else 1
            new_start = int(m.group(3))
            new_len = int(m.group(4)) if m.group(4) is not None else 1
            cur = Hunk(old_start, old_len, new_start, new_len, (m.group(5) or "").strip())
            result.hunks.append(cur)
            old_no, new_no, skipping = old_start, new_start, False
            continue

        if cur is None or skipping:
            continue  # file metadata before the first hunk, or inside a bad hunk
        if raw.startswith("\\"):
            continue  # "\ No newline at end of file"

        tag, text = raw[:1], raw[1:]
        if tag == "+":
            cur.lines.append(DiffLine("add", text, None, new_no))
            new_no += 1
        elif tag == "-":
            cur.lines.append(DiffLine("del", text, old_no, None))
            old_no += 1
        elif tag == " " or (raw == "" and cur.old_count < cur.old_len and cur.new_count < cur.new_len):
            # a blank line is a context line whose single space was stripped by some tool
            cur.lines.append(DiffLine("ctx", text, old_no, new_no))
            old_no += 1
            new_no += 1
        else:
            result.warnings.append(f"ignored unexpected line: {raw[:40]!r}")

    _check_counts(cur, result.warnings)
    return result
