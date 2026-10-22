import json

import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.github.signature import verify_signature

log = structlog.get_logger()
router = APIRouter()

HANDLED_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}


@router.post("/webhooks/github", status_code=202)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()

    # 1. Authenticity
        if not verify_signature(settings.github_webhook_secret, body, x_hub_signature_256):
        log.warning(
            "bad_signature",
            secret_len=len(settings.github_webhook_secret),
            body_len=len(body),
            has_header=bool(x_hub_signature_256),
            event=x_github_event,
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    # 2. Idempotency: same delivery id is processed only once (24h window)
    redis = request.app.state.redis
    is_new = await redis.set(f"gh:delivery:{x_github_delivery}", "1", nx=True, ex=86400)
    if not is_new:
        return {"status": "duplicate"}

    if x_github_event == "ping":
        return {"status": "pong"}

    payload = json.loads(body)

    # 3. Only enqueue what we care about; respond fast, work happens in worker
    if x_github_event == "pull_request" and payload.get("action") in HANDLED_ACTIONS:
        pr = payload["pull_request"]
        if pr.get("draft"):
            return {"status": "ignored", "reason": "draft"}

        repo = payload["repository"]["full_name"]
        job = {
            "installation_id": payload["installation"]["id"],
            "repo": repo,
            "number": pr["number"],
            "head_sha": pr["head"]["sha"],
            "action": payload["action"],
        }
        # _job_id => same (repo, PR, sha) cannot be queued twice
        await request.app.state.queue.enqueue_job(
            "review_pull_request", job, _job_id=f"{repo}#{pr['number']}@{pr['head']['sha']}"
        )
        log.info("queued", **job)
        return {"status": "queued"}

    return {"status": "ignored"}
