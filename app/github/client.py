from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger()
API = "https://api.github.com"
RETRY_STATUS = {429, 502, 503, 504}


async def _sleep(seconds: float) -> None:  # module-level so tests can replace it
    await asyncio.sleep(seconds)


class GitHubClient:
    """Thin async GitHub REST client using an installation token."""

    def __init__(self, token: str, *, transport: httpx.AsyncBaseTransport | None = None, base_url: str = API):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        resp: httpx.Response | None = None
        for attempt in range(3):
            resp = await self._client.request(method, url, **kwargs)
            retry_after = resp.headers.get("retry-after")
            transient = resp.status_code in RETRY_STATUS or (resp.status_code == 403 and retry_after)
            if not transient or attempt == 2:
                break
            delay = min(float(retry_after), 30) if retry_after else 2.0**attempt
            log.warning("github_retry", status=resp.status_code, url=url, delay=delay)
            await _sleep(delay)
        assert resp is not None
        return resp

    async def get_pr(self, repo: str, number: int) -> dict[str, Any]:
        resp = await self._request("GET", f"/repos/{repo}/pulls/{number}")
        resp.raise_for_status()
        return resp.json()

    async def list_pr_files(self, repo: str, number: int, max_pages: int = 30) -> list[dict[str, Any]]:
        """All changed files, 100 per page (GitHub caps a PR at 3000 files)."""
        files: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            resp = await self._request(
                "GET", f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100, "page": page}
            )
            resp.raise_for_status()
            batch = resp.json()
            files.extend(batch)
            if len(batch) < 100:
                break
        return files

    async def create_review(self, repo: str, number: int, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"/repos/{repo}/pulls/{number}/reviews"
        resp = await self._request("POST", url, json=payload)
        if resp.status_code == 422 and payload.get("comments"):
            # One bad line position rejects the whole review. Fall back to a summary-only
            # review that still carries every comment, instead of posting nothing.
            log.warning("review_422_fallback", repo=repo, number=number, comments=len(payload["comments"]))
            lines = [
                f"- `{c['path']}:{c.get('line')}`\n\n  {c['body']}".replace("\n", "\n  ")
                for c in payload["comments"]
            ]
            body = payload["body"] + "\n\n---\n**Comments that could not be attached inline:**\n\n" + "\n".join(lines)
            fallback = {**payload, "comments": [], "body": body[:60000]}
            resp = await self._request("POST", url, json=fallback)
        resp.raise_for_status()
        return resp.json()
