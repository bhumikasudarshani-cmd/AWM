"""Build the single batched review we post to a pull request."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.diff.mapping import Location, resolve_location
from app.pipeline.models import SEVERITY_ORDER, Finding, ReviewContext

MAX_BODY = 60000
BOT_NAME = "AWM"
STAGE_LABELS = {"rules": "security and debugging rules", "llm-security": "AI security review"}
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


def render_comment(f: Finding) -> str:
    parts = [f"**{SEVERITY_LABEL[f.severity]} · {f.category}**: {f.title}"]
    if f.explanation:
        parts.append(f.explanation)
    if f.suggested_fix:
        parts.append(f"**Suggested fix:** {f.suggested_fix}")
    sources = ", ".join(f"{e.tool}:{e.rule}" if e.rule else e.tool for e in f.evidence) or f.source_stage
    parts.append(f"<sub>confidence {f.confidence:.2f} · {sources}</sub>")
    return "\n\n".join(parts)


def _greeting(author: str) -> str:
    if author and not author.endswith("[bot]"):
        return f"Hi @{author}, I'm **{BOT_NAME}**."
    return f"Hi, I'm **{BOT_NAME}**."


def render_summary(
    ctx: ReviewContext,
    placed: list[PlacedFinding],
    outside: list[Finding],
    overflow_count: int,
    checks: tuple[str, ...] = (),
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
    partial = ctx.coverage.partial
    if partial:
        lines += ["", f"<details><summary>Only partly reviewed: {len(partial)} file(s)</summary>", ""]
        lines += [f"- `{s.path}`: {s.reason}" for s in partial[:15]]
        lines += ["", "</details>"]
    if all_findings:
        counts = {s: sum(1 for f in all_findings if f.severity == s) for s in SEVERITY_ORDER}
        breakdown = ", ".join(f"{counts[s]} {s}" for s in ("critical", "high", "medium", "low") if counts[s])
        lines.append(f"I found **{len(all_findings)}** thing(s) worth a look: {breakdown}.")
    else:
        lines.append("Nothing flagged by my checks. Nice work!")

    if outside:
        lines += ["", "**Findings outside the changed lines:**"]
        for f in outside:
            lines.append(f"- `{f.file}:{f.line_start}` **{f.title}**. {f.explanation}")
    if overflow_count:
        lines += ["", f"{overflow_count} lower-priority finding(s) were left out to keep this review short."]

    if skipped:
        lines += ["", f"<details><summary>Not reviewed: {len(skipped)} file(s)</summary>", ""]
        lines += [f"- `{s.path}`: {s.reason}" for s in skipped[:15]]
        if len(skipped) > 15:
            lines.append(f"- ... and {len(skipped) - 15} more")
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
    ctx: ReviewContext, placed: list[PlacedFinding], outside: list[Finding], overflow_count: int = 0,
    checks: tuple[str, ...] = (),
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
        "body": render_summary(ctx, placed, outside, overflow_count, checks),
        "comments": comments,
    }
