import asyncio

import pytest

from app.llm.base import LLMError, LLMOutputError
from app.llm.json_output import complete_findings, extract_json_object, parse_llm_findings
from tests.fakes import FakeProvider

GOOD = '{"findings":[{"file":"a.py","line":3,"severity":"high","confidence":0.9,"title":"SQL injection","explanation":"x"}]}'


def test_extract_plain_fenced_and_surrounded_json():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('Sure! Here you go:\n{"a": {"b": [1, 2]}}\nHope that helps.') == {"a": {"b": [1, 2]}}


def test_extract_skips_a_leading_brace_that_is_not_json():
    assert extract_json_object('Use {curly} braces. {"a": 1}') == {"a": 1}


def test_a_bare_list_is_treated_as_the_findings_list():
    assert extract_json_object('[{"x": 1}]') == {"findings": [{"x": 1}]}


@pytest.mark.parametrize("text", ["", "no json here", "{broken", "```json\n```"])
def test_extract_raises_on_garbage(text):
    with pytest.raises(LLMOutputError):
        extract_json_object(text)


def test_parse_returns_valid_findings():
    valid, bad = parse_llm_findings(GOOD)
    assert bad == 0 and valid[0].file == "a.py" and valid[0].line == 3 and valid[0].severity == "high"


def test_parse_drops_invalid_items_but_keeps_the_good_ones():
    text = ('{"findings":[{"file":"a.py","line":0,"severity":"high","confidence":0.9,"title":"t"},'
            '{"file":"a.py","line":2,"severity":"bogus","confidence":0.9,"title":"t"},'
            '{"file":"a.py","line":5,"severity":"low","confidence":0.5,"title":"ok"}, 42]}')
    valid, bad = parse_llm_findings(text)
    assert [f.title for f in valid] == ["ok"] and bad == 3


def test_parse_normalises_severity_case_and_percent_confidence():
    text = '{"findings":[{"file":"a.py","line":1,"severity":"HIGH","confidence":85,"title":"t"}]}'
    (f,), bad = parse_llm_findings(text)
    assert f.severity == "high" and f.confidence == pytest.approx(0.85) and bad == 0


def test_parse_requires_a_findings_list():
    with pytest.raises(LLMOutputError):
        parse_llm_findings('{"result": []}')
    assert parse_llm_findings('{"findings": []}') == ([], 0)


def test_complete_retries_once_with_a_hint_then_succeeds():
    provider = FakeProvider(["I could not do that", GOOD])
    valid, bad, responses = asyncio.run(complete_findings(provider, "sys", "user"))
    assert len(valid) == 1 and len(responses) == 2 and len(provider.calls) == 2
    assert "not valid JSON" in provider.calls[1]["user"]


def test_complete_gives_up_after_the_retry_budget():
    provider = FakeProvider(["nope"])
    with pytest.raises(LLMOutputError):
        asyncio.run(complete_findings(provider, "sys", "user", retries=1))
    assert len(provider.calls) == 2


def test_provider_errors_are_not_retried_as_bad_output():
    provider = FakeProvider([LLMError("boom")])
    with pytest.raises(LLMError):
        asyncio.run(complete_findings(provider, "sys", "user"))
    assert len(provider.calls) == 1
