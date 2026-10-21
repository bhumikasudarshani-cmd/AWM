from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.webhooks import router as webhooks_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.redis.aclose()
    await app.state.queue.aclose()


app = FastAPI(title="PR Reviewer", lifespan=lifespan)
app.include_router(webhooks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
