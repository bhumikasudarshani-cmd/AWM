"""Integration: webhook-to-review flow with the AI security stage switched on (fake model)."""
import asyncio
import json

import pytest

from app.llm.base import LLMError
from app.pipeline.stages.rules import RulesStage
from app.pipeline.stages.security_llm import LLMSecurityStage
from app.workers import tasks
from tests.fakes import FakeProvider
from tests.test_integration_webhook_to_review import (  # noqa: F401  (fixtures and helpers)
    FakeGitHub, demo_file, env, pr_event, run_worker, send, webhook_job,
)


def llm_reply(line, title="Unsafe command construction"):
    return json.dumps({"findings": [{"file": "demo_bad.py", "line": line, "severity": "high", "confidence": 0.8,
                                     "title": title, "explanation": "Input reaches a shell.", "suggested_fix": "Validate it."}]})


def use_stages(monkeypatch, provider, **kw):
    monkeypatch.setattr(tasks, "default_stages", lambda: [RulesStage(), LLMSecurityStage(provider, **kw)])


def test_ai_and_rule_findings_on_the_same_line_become_one_comment_with_both_sources(env, monkeypatch):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    use_stages(monkeypatch, FakeProvider([llm_reply(7)]))

    result = run_worker(redis, webhook_job(client, queue))

    assert result["status"] == "posted" and result["inline"] == 4  # not 5: line 7 is one comment
    (review,) = fake.reviews
    (on_7,) = [c["body"] for c in review["comments"] if c["line"] == 7]
    assert "Unsafe command construction" in on_7 and "High" in on_7
    assert "llm:security-reviewer" in on_7 and "rules:shell-true" in on_7
    assert "AI security review" in review["body"] and "**4** thing(s)" in review["body"]


@pytest.mark.parametrize("failure", ["not json at all", LLMError("model server down")])
def test_broken_model_never_blocks_the_review(env, monkeypatch, failure):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    use_stages(monkeypatch, FakeProvider([failure]), retries=0)

    result = run_worker(redis, webhook_job(client, queue))

    assert result["status"] == "posted" and result["inline"] == 4  # the four rule findings still arrive
    assert len(fake.reviews) == 1


def test_a_model_that_invents_locations_adds_nothing(env, monkeypatch):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    bad = json.dumps({"findings": [{"file": "other.py", "line": 1, "severity": "critical", "confidence": 1, "title": "x"},
                                   {"file": "demo_bad.py", "line": 500, "severity": "critical", "confidence": 1, "title": "y"}]})
    use_stages(monkeypatch, FakeProvider([bad]))

    assert run_worker(redis, webhook_job(client, queue))["inline"] == 4


def test_oversized_files_are_still_rule_checked_and_flagged_as_partly_reviewed(env, monkeypatch):
    redis, queue, client, install = env
    fake = FakeGitHub([demo_file()])
    install(fake)
    use_stages(monkeypatch, FakeProvider([llm_reply(7)]), max_input_tokens=50)

    result = run_worker(redis, webhook_job(client, queue))

    assert result["inline"] == 4
    assert "`demo_bad.py`: AI security review skipped: too large for one model call" in fake.reviews[0]["body"]
