from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import structlog

from app.pipeline.base import Stage
from app.pipeline.models import (
    SEVERITY_ORDER,
    Finding,
    ReviewConfig,
    ReviewContext,
    StageResult,
)

log = structlog.get_logger()


@dataclass(slots=True)
class PipelineResult:
    findings: list[Finding]
    stage_results: list[StageResult]
    dropped_unknown_file: int = 0


@dataclass(slots=True)
class Selection:
    selected: list[Finding] = field(default_factory=list)
    overflow: list[Finding] = field(default_factory=list)  # valid but cut by the comment cap
    below_threshold: int = 0  # dropped by min severity / confidence


def _sort_key(f: Finding) -> tuple:
    return (-SEVERITY_ORDER[f.severity], -f.confidence, f.file, f.line_start)


async def _run_stage(stage: Stage, ctx: ReviewContext, timeout: float) -> StageResult:
    started = time.perf_counter()
    try:
        findings = await asyncio.wait_for(stage.run(ctx), timeout=getattr(stage, "timeout", None) or timeout)
        error = None
    except Exception as exc:  # one broken stage must not sink the whole review
        findings, error = [], f"{type(exc).__name__}: {exc}"
        log.warning("stage_failed", stage=stage.name, error=error)
    duration_ms = int((time.perf_counter() - started) * 1000)
    stamped = [
        f.model_copy(update={"source_stage": stage.name}) if f.source_stage == "unknown" else f
        for f in findings
    ]
    return StageResult(stage.name, stamped, duration_ms, error)


async def run_pipeline(ctx: ReviewContext, stages: list[Stage], stage_timeout: float = 60.0) -> PipelineResult:
    """Run stages concurrently, then merge: drop unknown files, dedupe, sort."""
    results = await asyncio.gather(*(_run_stage(s, ctx, stage_timeout) for s in stages))

    known = ctx.files_by_path()
    best: dict[str, Finding] = {}
    dropped = 0
    for res in results:
        for f in res.findings:
            if f.file not in known:  # guards against invented file names later on
                dropped += 1
                continue
            key = f.fingerprint
            if key not in best:
                best[key] = f
            else:
                keep, other = (best[key], f) if best[key].confidence >= f.confidence else (f, best[key])
                keep.evidence.extend(e for e in other.evidence if e not in keep.evidence)
                best[key] = keep
    return PipelineResult(sorted(best.values(), key=_sort_key), list(results), dropped)


def select_findings(findings: list[Finding], cfg: ReviewConfig) -> Selection:
    """Precision-first filter: severity and confidence thresholds, then the comment cap."""
    min_sev = SEVERITY_ORDER[cfg.min_severity]
    kept = [
        f for f in findings
        if SEVERITY_ORDER[f.severity] >= min_sev and f.confidence >= cfg.min_confidence
    ]
    kept.sort(key=_sort_key)
    return Selection(
        selected=kept[: cfg.max_comments],
        overflow=kept[cfg.max_comments:],
        below_threshold=len(findings) - len(kept),
    )
