from __future__ import annotations

import time
from collections.abc import Callable

from app.eval.cases import Case, case_context
from app.eval.provider import CachingProvider
from app.eval.report import CaseResult, Summary, summarize
from app.eval.score import score_case
from app.pipeline.base import Stage
from app.pipeline.models import ReviewConfig
from app.pipeline.runner import run_pipeline, select_findings
from app.pipeline.stages.rules import RulesStage

CONFIG_NAMES = ("rules", "llm", "rules+llm")


async def evaluate(
    cases: list[Case],
    stage_factory: Callable[[], list[Stage]],
    cfg: ReviewConfig | None = None,
    provider: CachingProvider | None = None,
) -> list[CaseResult]:
    """Run the pipeline on every case and score what the author would actually see."""
    results: list[CaseResult] = []
    for case in cases:
        ctx = case_context(case, cfg)
        pt0 = provider.usage.prompt_tokens if provider else 0
        ct0 = provider.usage.completion_tokens if provider else 0
        started = time.perf_counter()
        piped = await run_pipeline(ctx, stage_factory())
        selected = select_findings(piped.findings, ctx.config).selected
        errors = [r.error for r in piped.stage_results if r.error]
        results.append(CaseResult(
            case_id=case.id, is_clean=case.is_clean, score=score_case(case.expected, selected),
            error="; ".join(errors) or None, duration_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=(provider.usage.prompt_tokens - pt0) if provider else 0,
            completion_tokens=(provider.usage.completion_tokens - ct0) if provider else 0,
        ))
    return results


def make_stage_factory(name: str, provider: CachingProvider | None, **llm_kwargs) -> Callable[[], list[Stage]]:
    if name not in CONFIG_NAMES:
        raise ValueError(f"unknown config {name!r}; choose from {CONFIG_NAMES}")
    if "llm" in name and provider is None:
        raise ValueError(f"config {name!r} needs a model provider")

    def factory() -> list[Stage]:
        stages: list[Stage] = []
        if "rules" in name:
            stages.append(RulesStage())
        if "llm" in name:
            from app.pipeline.stages.security_llm import LLMSecurityStage

            stages.append(LLMSecurityStage(provider, **llm_kwargs))
        return stages

    return factory


async def run_configs(
    cases: list[Case], names: list[str], provider: CachingProvider | None, **llm_kwargs
) -> dict[str, Summary]:
    out: dict[str, Summary] = {}
    for name in names:
        results = await evaluate(cases, make_stage_factory(name, provider, **llm_kwargs), provider=provider)
        out[name] = summarize(results)
    return out
