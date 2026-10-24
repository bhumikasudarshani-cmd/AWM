import asyncio
import json

import httpx
import pytest

from app.llm.base import LLMError, LLMOutputError
from app.llm.openai_compat import OpenAICompatProvider

OK = {"choices": [{"message": {"content": '{"findings": []}'}}], "usage": {"prompt_tokens": 120, "completion_tokens": 7}}


def provider(handler, api_key="", **kw):
    return OpenAICompatProvider("http://llm.test/v1/", "m1", api_key, transport=httpx.MockTransport(handler), **kw)


def test_request_shape_and_response_parsing():
    seen = {}

    def handler(request):
        seen["path"], seen["body"], seen["auth"] = request.url.path, json.loads(request.content), request.headers.get("authorization")
        return httpx.Response(200, json=OK)

    resp = asyncio.run(provider(handler).complete("SYS", "USER"))
    assert seen["path"] == "/v1/chat/completions" and seen["auth"] is None
    assert seen["body"]["model"] == "m1" and seen["body"]["temperature"] == 0
    assert seen["body"]["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert (resp.text, resp.prompt_tokens, resp.completion_tokens, resp.model) == ('{"findings": []}', 120, 7, "m1")
    assert resp.latency_ms >= 0


def test_api_key_is_sent_as_bearer_only_when_set():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=OK)

    asyncio.run(provider(handler, api_key="k123").complete("s", "u"))
    assert seen["auth"] == "Bearer k123"


def test_json_mode_can_be_switched_off():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK)

    asyncio.run(provider(handler).complete("s", "u", json_mode=False))
    assert "response_format" not in seen["body"]


def test_400_retries_once_without_json_mode():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(400, json={"error": "unsupported"}) if len(bodies) == 1 else httpx.Response(200, json=OK)

    resp = asyncio.run(provider(handler).complete("s", "u"))
    assert resp.text and "response_format" in bodies[0] and "response_format" not in bodies[1]


def test_http_error_and_timeout_become_llm_error_without_leaking_the_prompt():
    with pytest.raises(LLMError, match="HTTP 500"):
        asyncio.run(provider(lambda r: httpx.Response(500, text="server down")).complete("s", "SECRET-PROMPT"))

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError) as exc:
        asyncio.run(provider(slow).complete("s", "SECRET-PROMPT"))
    assert "SECRET-PROMPT" not in str(exc.value) and "ReadTimeout" in str(exc.value)


def test_unexpected_response_shape_is_an_output_error():
    with pytest.raises(LLMOutputError):
        asyncio.run(provider(lambda r: httpx.Response(200, json={"nope": 1})).complete("s", "u"))


def test_missing_usage_is_tolerated():
    body = {"choices": [{"message": {"content": "x"}}]}
    resp = asyncio.run(provider(lambda r: httpx.Response(200, json=body)).complete("s", "u"))
    assert resp.prompt_tokens is None and resp.completion_tokens is None
