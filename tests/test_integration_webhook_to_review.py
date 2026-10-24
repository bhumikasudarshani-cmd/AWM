"""Integration: signed webhook -> queue -> worker -> pipeline -> review payload.

GitHub is a fake server (httpx.MockTransport), Redis an in-memory stand-in, and the queue a recorder.
Everything between them is the real code.
"""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhooks import router
from app.config import settings
from app.github.client import GitHubClient
from app.workers import tasks

SECRET = "integration-secret"
REPO, NUMBER, SHA = "o/r", 5, "a" * 40

DEMO = [
    "import subprocess",
    "import requests",
    "",
    "",
    "def run(cmd):",
    "    breakpoint()",
    "    return subprocess.run(cmd, shell=True)",
    "",
    "",
    "def fetch(url):",
    "    return requests.get(url, verify=False)",
    "",
    "",
    'password = "hunter2hunter2"',
]
DEMO_PATCH = "@@ -0,0 +1,14 @@\n" + "\n".join("+" + line for line in DEMO)


class FakeRedis:
    """The few Redis calls the app uses, in memory."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def exists(self, key):
        return int(key in self.data)

    async def aclose(self):
        return None


class FakeQueue:
    def __init__(self, redis):
        self.jobs: list[tuple[str, dict, str]] = []
        self._redis = redis

    async def enqueue_job(self, name, job, _job_id=None):
        self.jobs.append((name, job, _job_id))


class FakeGitHub:
    """Serves the three endpoints the worker uses and records what it is sent."""

    def __init__(self, files, head_sha=SHA, state="open", review_status=(200,)):
        self.files, self.head_sha, self.state = files, head_sha, state
        self.review_statuses = list(review_status)
        self.reviews: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == f"/repos/{REPO}/pulls/{NUMBER}" and request.method == "GET":
            return httpx.Response(200, json={
                "state": self.state, "title": "Demo", "body": "", "user": {"login": "bhumi"},
                "head": {"sha": self.head_sha},
            })
        if path.endswith("/files"):
            return httpx.Response(200, json=self.files)
        if path.endswith("/reviews") and request.method == "POST":
            self.reviews.append(json.loads(request.content))
            status = self.review_statuses.pop(0) if len(self.review_statuses) > 1 else self.review_statuses[0]
            return httpx.Response(status, json={"id": len(self.reviews)})
        return httpx.Response(404)


def demo_file():
    return {"filename": "demo_bad.py", "status": "added", "additions": 14, "deletions": 0,
            "changes": 14, "patch": DEMO_PATCH}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SECRET)
    redis = FakeRedis()
    queue = FakeQueue(redis)
    app = FastAPI()
    app.include_router(router)
    app.state.redis, app.state.queue = redis, queue

    def install(fake: FakeGitHub):
        async def fake_token(_redis, _installation_id):
            return "tok"

        monkeypatch.setattr(tasks, "get_installation_token", fake_token)
        monkeypatch.setattr(
            tasks, "GitHubClient", lambda token: GitHubClient(token, transport=httpx.MockTransport(fake.handler))
        )

    return redis, queue, TestClient(app), install


def pr_event(action="opened", draft=False):
    return json.dumps({
        "action": action,
        "pull_request": {"number": NUMBER, "draft": draft, "head": {"sha": SHA}},
        "repository": {"full_name": REPO},
        "installation": {"id": 99},
    }).encode()


def send(client, body, delivery="d1", event="pull_request", secret=SECRET):
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig,
    })


def run_worker(redis, job):
    return asyncio.run(tasks.review_pull_request({"redis_client": redis}, job))


# ---------------- webhook intake ----------------

def test_valid_webhook_queues_exactly_one_idempotent_job(env):
    _, queue, client, _ = env
    r = send(client, pr_event())
    assert r.status_code == 202 and r.json() == {"status": "queued"}
    (name, job, job_id), = queue.jobs
    assert name == "review_pull_request" and job_id == f"{REPO}#{NUMBER}@{SHA}"
    assert job["installation_id"] == 99 and job["head_sha"] == SHA


def test_redelivered_webhook_is_not_queued_twice(env):
    _, queue, client, _ = env
    send(client, pr_event(), delivery="same")
    r = send(client, pr_event(), delivery="same")
    assert r.json() == {"status": "duplicate"} and len(queue.jobs) == 1


def test_bad_signature_is_rejected_and_nothing_is_queued(env):
    _, queue, client, _ = env
    r = send(client, pr_event(), secret="wrong-secret")
    assert r.status_code == 401 and queue.jobs == []


@pytest.mark.parametrize("event,body,reason", [
    ("pull_request", pr_event(draft=True), "draft"),
    ("pull_request", pr_event(action="closed"), None),
    ("issue_comment", b"{}", None),
])
def test_irrelevant_events_are_ignored(env, event, body, reason):
    _, queue, client, _ = env
    r = send(client, body, event=event, delivery=f"{event}-{len(body)}")
    assert r.status_code == 202 and r.json()["status"] == "ignored" and queue.jobs == []
    if reason:
        assert r.json()["reason"] == reason


# ---------------- worker: full review ----------------

def webhook_job(client, queue):
    send(client, pr_event())
    return queue.jobs[0][1]


def test_full_flow_posts_one_review_with_comments_on_the_right_lines(env):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)

    result = run_worker(redis, webhook_job(client, queue))

    assert result["status"] == "posted" and result["inline"] == 4
    (review,) = fake.reviews
    assert review["commit_id"] == SHA and review["event"] == "COMMENT"
    by_line = {c["line"]: c["body"] for c in review["comments"]}
    assert sorted(by_line) == [6, 7, 11, 14]
    assert "Debugger call left in code" in by_line[6]
    assert "shell=True" in by_line[7]
    assert "TLS certificate verification disabled" in by_line[11]
    assert "hardcoded credential" in by_line[14]
    assert all(c["path"] == "demo_bad.py" and c["side"] == "RIGHT" for c in review["comments"])
    assert "Hi @bhumi, I'm **AWM**." in review["body"] and "**4** thing(s)" in review["body"]
    assert "hunter2hunter2" not in review["body"]  # the secret is never echoed in text we write


def test_same_commit_is_never_reviewed_twice(env):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    job = webhook_job(client, queue)
    run_worker(redis, job)
    assert run_worker(redis, job)["status"] == "already_posted"
    assert len(fake.reviews) == 1


def test_new_commit_does_not_repeat_findings_already_posted(env):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    job = webhook_job(client, queue)
    run_worker(redis, job)

    newer = "b" * 40
    fake.head_sha = newer
    job2 = {**job, "head_sha": newer}
    run_worker(redis, job2)

    assert len(fake.reviews) == 2
    assert fake.reviews[1]["comments"] == []  # same four findings, same code: not repeated
    assert "Nothing flagged" in fake.reviews[1]["body"]


def test_stale_job_is_skipped_when_the_pr_moved_on_or_closed(env):
    redis, queue, client, install = env
    job = webhook_job(client, queue)

    fake = FakeGitHub([demo_file()], head_sha="c" * 40)
    install(fake)
    assert run_worker(redis, job)["status"] == "stale"

    fake_closed = FakeGitHub([demo_file()], state="closed")
    install(fake_closed)
    assert run_worker(redis, job)["status"] == "stale"
    assert fake.reviews == [] and fake_closed.reviews == []


def test_awkward_files_never_break_the_review_and_are_listed_as_skipped(env):
    redis, queue, client, install = env
    files = [
        demo_file(),
        {"filename": "logo.png", "status": "added", "additions": 0, "deletions": 0, "changes": 0},
        {"filename": "yarn.lock", "status": "modified", "additions": 3, "deletions": 0, "changes": 3,
         "patch": "@@ -1 +1,2 @@\n a\n+b"},
        {"filename": "big.py", "status": "modified", "additions": 900, "deletions": 0, "changes": 900},
        {"filename": "new_name.py", "status": "renamed", "previous_filename": "old_name.py",
         "additions": 0, "deletions": 0, "changes": 0},
        {"filename": "weird.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1,
         "patch": "not a diff at all"},
    ]
    fake = FakeGitHub(files)
    install(fake)

    result = run_worker(redis, webhook_job(client, queue))

    assert result["status"] == "posted" and result["inline"] == 4
    body = fake.reviews[0]["body"]
    for name, reason in [("logo.png", "binary file"), ("yarn.lock", "lockfile"),
                         ("big.py", "diff too large for GitHub to return"),
                         ("new_name.py", "no textual changes"), ("weird.py", "could not parse")]:
        assert f"`{name}`: {reason}" in body


def test_rejected_inline_comments_fall_back_to_a_summary_only_review(env):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()], review_status=(422, 200))
    install(fake)

    result = run_worker(redis, webhook_job(client, queue))

    assert result["status"] == "posted" and len(fake.reviews) == 2
    assert fake.reviews[1]["comments"] == []
    assert "could not be attached inline" in fake.reviews[1]["body"]
    assert "shell=True" in fake.reviews[1]["body"]
