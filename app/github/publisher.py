"""Build the single batched review we post to a pull request."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.diff.mapping import Location, resolve_location
from app.pipeline.models import SEVERITY_ORDER, Finding, ReviewContext
from app.sanitize import inline_code, sanitize_text

MAX_BODY = 60000
MAX_TITLE = 200
MAX_EXPLANATION = 1500
MAX_FIX = 1000
MAX_REASON = 200
MAX_PATH = 200
_LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,38}")  # a GitHub login; "dependabot[bot]" and anything odd do not match
BOT_NAME = "AWM"
STAGE_LABELS = {"rules": "security and debugging rules", "llm-security": "AI security review"}  # friendly names for the "checks run" line
SEVERITY_LABEL = {"low": "Low", "medium": "Medium", "high": "High", "critical": "Critical"}


@dataclass(frozen=True, slots=True)
class PlacedFinding:
    finding: Finding
    location: Location


def place_findings(ctx: ReviewContext, findings: list[Finding]) -> tuple[list[PlacedFinding], list[Finding]]:
    """Split findings into those GitHub can attach inline and those outside the diff."""
    files = ctx.files_by_path()
    placed: list[PlacedFinding] = []
    outside: list[Finding] = []
    for f in findings:
        fd = files.get(f.file)
        loc = resolve_location(fd, f.line_start, f.line_end) if fd else None
        if loc is None:
            outside.append(f)
        else:
            placed.append(PlacedFinding(f, loc))
    return placed, outside


def _one_line(text: str, limit: int) -> str:
    return sanitize_text(" ".join(text.split()), limit)


def render_comment(f: Finding) -> str:
    # The model reads code an attacker may have written, so what it wrote back is untrusted: clean all of it.
    parts = [f"**{SEVERITY_LABEL[f.severity]} · {f.category}**: {_one_line(f.title, MAX_TITLE)}"]
    explanation = sanitize_text(f.explanation, MAX_EXPLANATION)
    if explanation:
        parts.append(explanation)
    fix = sanitize_text(f.suggested_fix or "", MAX_FIX)
    if fix:
        parts.append(f"**Suggested fix:** {fix}")
    sources = ", ".join(f"{e.tool}:{e.rule}" if e.rule else e.tool for e in f.evidence) or f.source_stage
    parts.append(f"<sub>confidence {f.confidence:.2f} · {sources}</sub>")
    return "\n\n".join(parts)


def _greeting(author: str) -> str:
    # @-mention people so they get notified; skip bots (for example dependabot[bot]) and anything that is not a login
    if _LOGIN.fullmatch(author or ""):
        return f"Hi @{author}, I'm **{BOT_NAME}**."
    return f"Hi, I'm **{BOT_NAME}**."


def render_summary(
    ctx: ReviewContext,
    placed: list[PlacedFinding],
    outside: list[Finding],
    overflow_count: int,
    checks: tuple[str, ...] = (),
    held_back: int = 0,
) -> str:
    all_findings = [p.finding for p in placed] + outside
    reviewed, skipped = len(ctx.coverage.reviewed), ctx.coverage.skipped
    changed = sum(f.changed_lines for f in ctx.files)
    lines = [
        f"### \U0001F44B {_greeting(ctx.author)}",
        "",
        f"I looked at your changes in `{ctx.head_sha[:7]}`: **{reviewed}** file(s), **{changed}** changed line(s).",
        "",
    ]

    if all_findings:
        counts = {s: sum(1 for f in all_findings if f.severity == s) for s in SEVERITY_ORDER}
        breakdown = ", ".join(f"{counts[s]} {s}" for s in ("critical", "high", "medium", "low") if counts[s])
        lines.append(f"I found **{len(all_findings)}** thing(s) worth a look: {breakdown}.")
    else:
        lines.append("Nothing flagged by my checks. Nice work!")

    if outside:
        lines += ["", "**Findings outside the changed lines:**"]
        for f in outside:
            where = inline_code(f"{f.file}:{f.line_start}", MAX_PATH)
            lines.append(f"- {where} **{_one_line(f.title, MAX_TITLE)}**. {_one_line(f.explanation, MAX_EXPLANATION)}")
    if overflow_count:
        lines += ["", f"{overflow_count} lower-priority finding(s) were left out to keep this review short."]

    if skipped:
        lines += ["", f"<details><summary>Not reviewed: {len(skipped)} file(s)</summary>", ""]
        lines += [f"- {inline_code(s.path, MAX_PATH)}: {_one_line(s.reason, MAX_REASON)}" for s in skipped[:15]]
        if len(skipped) > 15:
            lines.append(f"- ... and {len(skipped) - 15} more")
        lines += ["", "</details>"]

    if held_back:
        lines += ["", f"I held back {held_back} pattern match(es) that the AI review did not confirm."]

    partial = ctx.coverage.partial
    if partial:
        lines += ["", f"<details><summary>Only partly reviewed: {len(partial)} file(s)</summary>", ""]
        lines += [f"- {inline_code(s.path, MAX_PATH)}: {_one_line(s.reason, MAX_REASON)}" for s in partial[:15]]
        lines += ["", "</details>"]

    if checks:
        labels = ", ".join(STAGE_LABELS.get(c, c) for c in checks)
        lines += ["", f"<sub>Checks run: {labels}</sub>"]
    lines += [
        f"<sub>{BOT_NAME} is automated and can be wrong, so please use your own judgement.</sub>",
        "",
        f"<!-- awm-reviewer sha={ctx.head_sha} -->",
    ]
    return "\n".join(lines)[:MAX_BODY]


def build_review_payload(
    ctx: ReviewContext,
    placed: list[PlacedFinding],
    outside: list[Finding],
    overflow_count: int = 0,
    checks: tuple[str, ...] = (),
    held_back: int = 0,
) -> dict[str, Any]:
    comments: list[dict[str, Any]] = []
    for p in placed:
        c: dict[str, Any] = {
            "path": p.finding.file,
            "line": p.location.line,
            "side": "RIGHT",
            "body": render_comment(p.finding),
        }
        if p.location.start_line is not None:
            c["start_line"] = p.location.start_line
            c["start_side"] = "RIGHT"
        comments.append(c)
    return {
        "commit_id": ctx.head_sha,
        "event": "COMMENT",
        "body": render_summary(ctx, placed, outside, overflow_count, checks, held_back),
        "comments": comments,
    }
