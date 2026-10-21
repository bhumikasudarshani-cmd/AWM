import time

import httpx
import jwt
from redis.asyncio import Redis

from app.config import settings

API = "https://api.github.com"


def make_app_jwt() -> str:
    """Short-lived JWT that authenticates us *as the GitHub App*."""
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.github_app_id}
    return jwt.encode(payload, settings.private_key_pem, algorithm="RS256")


async def get_installation_token(redis: Redis, installation_id: int) -> str:
    """Installation access token (valid ~1h). Cached in Redis for 50 min."""
    key = f"gh:token:{installation_id}"
    cached = await redis.get(key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {make_app_jwt()}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
    token = r.json()["token"]
    await redis.set(key, token, ex=50 * 60)
    return token
