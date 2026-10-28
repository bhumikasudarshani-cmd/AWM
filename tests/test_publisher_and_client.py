import asyncio
import json

import httpx

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage, SkippedFile
from app.github import client as client_mod
from app.github.client import GitHubClient
from app.github.publisher import build_review_payload, place_findings
from app.pipeline.models import Evidence, Finding, ReviewContext

PATCH = "@@ -1,2 +1,3 @@\n a\n+b\n c"


def ctx_with(findings_files=("a.py",)):
    fds = [build_file_diff({"filename": n, "status": "modified", "changes": 1, "additions": 1, "patch": PATCH}) for n in findings_files]
    cov = Coverage(reviewed=[f.path for f in fds], skipped=[SkippedFile("yarn.lock", "lockfile")])
    return ReviewContext("o/r", 7, "abcdef1234567", "t", "", "me", fds, cov)


def finding(line, **kw):
    base = dict(file="a.py", line_start=line, line_end=line, category="security", severity="high", confidence=0.8,
                title="Bad thing", explanation="Because.", suggested_fix="Do better.", evidence=[Evidence(tool="rules", rule="r")])
    base.update(kw)
    return Finding(**base)


def test_inline_vs_outside_diff_placement():
    ctx = ctx_with()
    placed, outside = place_findings(ctx, [finding(2), finding(99)])
    assert [p.location.line for p in placed] == [2]
    assert [f.line_start for f in outside] == [99]


def test_payload_shape_and_summary_contents():
    ctx = ctx_with()
    placed, outside = place_findings(ctx, [finding(2), finding(99)])
    payload = build_review_payload(ctx, placed, outside, overflow_count=2)
    assert payload["commit_id"] == ctx.head_sha and payload["event"] == "COMMENT"
    (c,) = payload["comments"]
    assert c["path"] == "a.py" and c["line"] == 2 and c["side"] == "RIGHT"
    assert "Suggested fix" in c["body"] and "rules:r" in c["body"]
    body = payload["body"]
    assert "**2** thing(s)" in body and "outside the changed lines" in body
    assert "2 lower-priority" in body and "yarn.lock" in body and "lockfile" in body
    assert "awm-reviewer sha=abcdef1234567" in body


def test_clean_review_says_so():
    ctx = ctx_with()
    payload = build_review_payload(ctx, [], [])
    assert "Nothing flagged" in payload["body"] and payload["comments"] == []


def test_multiline_comment_has_start_line():
    ctx = ctx_with()
    placed, outside = place_findings(ctx, [finding(1, line_end=3)])
    (c,) = build_review_payload(ctx, placed, outside)["comments"]
    assert (c["start_line"], c["line"]) == (1, 3)


def test_create_review_falls_back_to_summary_on_422():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if body["comments"]:
            return httpx.Response(422, json={"message": "Unprocessable"})
        return httpx.Response(200, json={"id": 1})

    async def go():
        async with GitHubClient("tok", transport=httpx.MockTransport(handler)) as gh:
            payload = {"commit_id": "c", "event": "COMMENT", "body": "summary",
                       "comments": [{"path": "a.py", "line": 2, "side": "RIGHT", "body": "hello"}]}
            return await gh.create_review("o/r", 1, payload)

    assert asyncio.run(go()) == {"id": 1}
    assert len(seen) == 2 and seen[1]["comments"] == []
    assert "could not be attached inline" in seen[1]["body"] and "hello" in seen[1]["body"]


def test_list_pr_files_paginates():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        n = 100 if page == 1 else 7
        return httpx.Response(200, json=[{"filename": f"f{page}_{i}"} for i in range(n)])

    async def go():
        async with GitHubClient("tok", transport=httpx.MockTransport(handler)) as gh:
            return await gh.list_pr_files("o/r", 1)

    assert len(asyncio.run(go())) == 107


def test_retries_transient_errors(monkeypatch):
    calls = {"n": 0}

    async def no_sleep(_):
        return None

    monkeypatch.setattr(client_mod, "_sleep", no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    async def go():
        async with GitHubClient("tok", transport=httpx.MockTransport(handler)) as gh:
            return await gh.get_pr("o/r", 1)

    assert asyncio.run(go()) == {"ok": True} and calls["n"] == 3

def test_summary_greets_the_author_and_names_the_bot():
    ctx = ctx_with()
    ctx.author = "bhumi"
    body = build_review_payload(ctx, [], [], checks=("rules",))["body"]
    assert "Hi @bhumi, I'm **AWM**." in body
    assert "Checks run: security and debugging rules" in body


def test_summary_does_not_mention_bots_or_empty_authors():
    for author in ("dependabot[bot]", ""):
        ctx = ctx_with()
        ctx.author = author
        body = build_review_payload(ctx, [], [])["body"]
        assert "Hi, I'm **AWM**." in body
