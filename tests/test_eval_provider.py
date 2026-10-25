import asyncio

import pytest

from app.eval.provider import CachingProvider
from app.llm.base import LLMError
from tests.fakes import FakeProvider


def call(provider, system="s", user="u", json_mode=True):
    return asyncio.run(provider.complete(system, user, json_mode=json_mode))


def test_record_then_replay_returns_the_same_answer_without_calling_the_model(tmp_path):
    live = FakeProvider(["answer-1", "answer-2"], model="m")
    rec = CachingProvider(live, tmp_path, mode="record")
    assert call(rec).text == "answer-1" and len(live.calls) == 1

    replay_inner = FakeProvider(["SHOULD-NOT-BE-USED"], model="m")
    rep = CachingProvider(replay_inner, tmp_path, mode="replay")
    assert call(rep).text == "answer-1" and replay_inner.calls == []
    assert rep.usage.cached == 1


def test_replay_without_a_recording_fails_loudly(tmp_path):
    rep = CachingProvider(None, tmp_path, mode="replay", model="m")
    with pytest.raises(LLMError, match="no recorded response"):
        call(rep)


def test_live_mode_never_reads_or_writes_the_cache(tmp_path):
    inner = FakeProvider(["a", "b"], model="m")
    live = CachingProvider(inner, tmp_path, mode="live")
    assert [call(live).text, call(live).text] == ["a", "b"] and list(tmp_path.iterdir()) == []


def test_record_mode_reuses_an_existing_recording(tmp_path):
    inner = FakeProvider(["first", "second"], model="m")
    rec = CachingProvider(inner, tmp_path, mode="record")
    call(rec)
    assert call(rec).text == "first" and len(inner.calls) == 1


def test_cache_key_depends_on_model_prompt_and_json_mode(tmp_path):
    inner = FakeProvider(["x"], model="m1")
    rec = CachingProvider(inner, tmp_path, mode="record")
    call(rec); call(rec, system="other"); call(rec, user="other"); call(rec, json_mode=False)
    other_model = CachingProvider(FakeProvider(["x"], model="m2"), tmp_path, mode="record")
    call(other_model)
    assert len(list(tmp_path.glob("*.json"))) == 5


def test_usage_totals_include_cached_tokens_and_aclose_keeps_the_shared_provider_open(tmp_path):
    inner = FakeProvider(["x"], model="m")
    rec = CachingProvider(inner, tmp_path, mode="record")
    call(rec, user="a" * 40); call(rec, user="a" * 40)
    assert rec.usage.calls == 1 and rec.usage.cached == 1
    assert rec.usage.prompt_tokens == 20 and rec.usage.completion_tokens == 20
    asyncio.run(rec.aclose())
    assert inner.closed is False
    asyncio.run(rec.close())
    assert inner.closed is True


def test_replay_never_falls_back_to_the_live_model_even_when_one_is_available(tmp_path):
    inner = FakeProvider(["live answer"], model="m")
    rep = CachingProvider(inner, tmp_path, mode="replay")
    with pytest.raises(LLMError, match="no recorded response"):
        call(rep)
    assert inner.calls == []  # a replay run must never spend money
