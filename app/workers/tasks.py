import structlog
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings
from app.diff.builder import build_file_diff
from app.diff.coverage import apply_limits
from app.diff.dump import dump_files
from app.github.app_auth import get_installation_token
from app.github.client import GitHubClient
from app.github.publisher import build_review_payload, place_findings
from app.pipeline.models import ReviewConfig, ReviewContext
from app.pipeline.runner import run_pipeline, select_findings
from app.pipeline.stages import default_stages

log = structlog.get_logger()

POSTED_TTL = 60 * 60 * 24 * 30  # remember posted findings for 30 days


async def startup(ctx):
    ctx["redis_client"] = Redis.from_url(settings.redis_url, decode_responses=True)


async def shutdown(ctx):
    await ctx["redis_client"].aclose()


async def review_pull_request(ctx, job: dict):
    redis: Redis = ctx["redis_client"]
    repo, number, sha = job["repo"], job["number"], job["head_sha"]

    guard_key = f"review:posted:{repo}#{number}@{sha}"
    if await redis.exists(guard_key):
        log.info("review_already_posted", repo=repo, pr=number, sha=sha[:7])
        return {"status": "already_posted"}

    token = await get_installation_token(redis, job["installation_id"])
    cfg = ReviewConfig()

    async with GitHubClient(token) as gh:
        pr = await gh.get_pr(repo, number)
        if pr.get("state") != "open" or pr["head"]["sha"] != sha:
            log.info("review_stale", repo=repo, pr=number, sha=sha[:7])
            return {"status": "stale"}

        raw_files = await gh.list_pr_files(repo, number)
        if settings.dump_fixtures:
            path = dump_files(repo, number, sha, raw_files)
            log.info("fixture_dumped", path=str(path))

        files = [build_file_diff(f, cfg.ignore_paths) for f in raw_files]
        reviewed, coverage = apply_limits(files, cfg.limits)
        rctx = ReviewContext(
            repo=repo, number=number, head_sha=sha,
            title=pr.get("title") or "", body=pr.get("body") or "",
            author=(pr.get("user") or {}).get("login", ""),
            files=reviewed, coverage=coverage, config=cfg,
        )

        stages = default_stages()
        result = await run_pipeline(rctx, stages)
        selection = select_findings(result.findings, cfg)

        # do not repeat a finding we already commented on in an earlier push of this PR
        fresh = []
        for f in selection.selected:
            if not await redis.exists(f"finding:posted:{repo}#{number}:{f.fingerprint}"):
                fresh.append(f)

        placed, outside = place_findings(rctx, fresh)
        if not (placed or outside or selection.overflow) and not cfg.post_when_clean:
            return {"status": "clean_not_posted"}

        payload = build_review_payload(
            rctx, placed, outside, len(selection.overflow), checks=tuple(st.name for st in stages)
        )
        await gh.create_review(repo, number, payload)

    await redis.set(guard_key, "1", ex=POSTED_TTL)
    for f in fresh:
        await redis.set(f"finding:posted:{repo}#{number}:{f.fingerprint}", "1", ex=POSTED_TTL)

    log.info(
        "review_posted", repo=repo, pr=number, files_reviewed=len(reviewed),
        files_skipped=len(coverage.skipped), inline=len(placed), outside=len(outside),
        below_threshold=selection.below_threshold, stage_errors=[r.stage for r in result.stage_results if r.error],
    )
    return {"status": "posted", "inline": len(placed), "outside": len(outside)}


class WorkerSettings:
    functions = [review_pull_request]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3
    job_timeout = 600
