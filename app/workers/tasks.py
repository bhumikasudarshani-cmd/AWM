import httpx
import structlog
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.config import settings
from app.github.app_auth import get_installation_token

log = structlog.get_logger()


async def startup(ctx):
    ctx["redis_client"] = Redis.from_url(settings.redis_url, decode_responses=True)


async def shutdown(ctx):
    await ctx["redis_client"].aclose()


async def review_pull_request(ctx, job: dict):
    """Day 1: fetch the diff and log it. Pipeline stages plug in here from Day 2."""
    token = await get_installation_token(ctx["redis_client"], job["installation_id"])

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"https://api.github.com/repos/{job['repo']}/pulls/{job['number']}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.diff",  # raw unified diff
            },
        )
        r.raise_for_status()

    diff = r.text
    log.info("diff_fetched", repo=job["repo"], pr=job["number"], chars=len(diff))
    # TODO Day 2: parse diff -> ReviewContext -> run stages -> publish review
    return {"chars": len(diff)}


class WorkerSettings:
    functions = [review_pull_request]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3
    job_timeout = 600
