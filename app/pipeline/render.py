"""Render diffs for a model, and split them into calls that fit its context window.

Every code line starts with a line number or a marker, so text inside the diff can never look like
one of our own delimiters (a cheap defence against prompt injection through code).
"""
from __future__ import annotations

from app.diff.models import FileDiff


def estimate_tokens(text: str) -> int:
    # Rough and deliberately pessimistic for code; replace with a real tokenizer if one is needed.
    return len(text) // 3 + 1


def render_file(fd: FileDiff) -> str:
    out = [f"=== FILE: {fd.path} ==="]
    for h in fd.hunks:
        rng = h.new_range
        header = f"@@ lines {rng[0]}-{rng[1]} @@" if rng else "@@ deletions only @@"
        out.append(f"{header} {h.section}".rstrip())
        for ln in h.lines:
            if ln.kind == "add":
                out.append(f"{ln.new_no:>5} + {ln.text}")
            elif ln.kind == "ctx":
                out.append(f"{ln.new_no:>5}   {ln.text}")
            else:
                out.append(f"{'':>5} - {ln.text}")
    return "\n".join(out)


def plan_batches(
    files: list[FileDiff], max_tokens: int, max_calls: int
) -> tuple[list[list[FileDiff]], list[tuple[str, str]]]:
    """Group files, in order, into batches under max_tokens. Returns (batches, [(path, reason)])."""
    batches: list[list[FileDiff]] = []
    skipped: list[tuple[str, str]] = []
    current: list[FileDiff] = []
    used = 0
    for fd in files:
        cost = estimate_tokens(render_file(fd))
        if cost > max_tokens:
            skipped.append((fd.path, "too large for one model call"))
            continue
        if current and used + cost > max_tokens:
            batches.append(current)
            current, used = [], 0
        if not current and len(batches) >= max_calls:
            skipped.append((fd.path, "over the model call cap"))
            continue
        current.append(fd)
        used += cost
    if current:
        batches.append(current)
    return batches, skipped
