"""One adapter for every OpenAI-compatible endpoint: Ollama, Groq, OpenRouter, Gemini, OpenAI."""
from __future__ import annotations

import time

import httpx

from app.llm.base import LLMError, LLMOutputError, LLMResponse


class OpenAICompatProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        *,
        timeout: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, headers=headers, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, body: dict) -> httpx.Response:
        try:
            return await self._client.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:  # timeouts, connection errors; never include the request body
            raise LLMError(f"request failed: {type(exc).__name__}") from exc

    async def complete(self, system: str, user: str, *, json_mode: bool = True) -> LLMResponse:
        body: dict = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        resp = await self._post(body)
        if resp.status_code == 400 and "response_format" in body:
            body.pop("response_format")  # some servers do not support JSON mode; try once without
            resp = await self._post(body)
        if resp.status_code >= 400:
            raise LLMError(f"LLM returned HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMOutputError("unexpected response shape from the model server") from exc

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
