"""Record and replay model answers so an evaluation can be repeated for free and offline.

  live    call the model every time, store nothing
  record  call the model on a cache miss and store the answer
  replay  never call the model; a missing recording is an error
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.llm.base import LLMError, LLMProvider, LLMResponse


@dataclass(slots=True)
class Usage:
    calls: int = 0  # real model calls
    cached: int = 0  # answers served from recordings
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class CachingProvider:
    def __init__(self, inner: LLMProvider | None, cache_dir: str | Path, mode: str = "replay", model: str = ""):
        if mode not in ("live", "record", "replay"):
            raise ValueError(f"unknown mode {mode!r}")
        self._inner = inner
        self._dir = Path(cache_dir)
        self._mode = mode
        self._model = model
        self.usage = Usage()

    @property
    def model(self) -> str:
        return self._inner.model if self._inner is not None else self._model

    def _path(self, system: str, user: str, json_mode: bool) -> Path:
        key = hashlib.sha256(f"{self.model}\0{system}\0{user}\0{json_mode}".encode()).hexdigest()[:32]
        return self._dir / f"{key}.json"

    def _add(self, r: LLMResponse) -> None:
        self.usage.prompt_tokens += r.prompt_tokens or 0
        self.usage.completion_tokens += r.completion_tokens or 0
        self.usage.latency_ms += r.latency_ms

    async def complete(self, system: str, user: str, *, json_mode: bool = True) -> LLMResponse:
        path = self._path(system, user, json_mode)
        if self._mode != "live" and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            resp = LLMResponse(data["text"], data["model"], data["prompt_tokens"], data["completion_tokens"], data["latency_ms"])
            self.usage.cached += 1
            self._add(resp)
            return resp
        if self._mode == "replay" or self._inner is None:
            raise LLMError("no recorded response for this prompt (run with --mode record first)")
        resp = await self._inner.complete(system, user, json_mode=json_mode)
        self.usage.calls += 1
        self._add(resp)
        if self._mode == "record":
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "text": resp.text, "model": resp.model, "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens, "latency_ms": resp.latency_ms,
            }), encoding="utf-8")
        return resp

    async def aclose(self) -> None:
        """No-op: the stage closes its provider after every case, but this one is shared by all cases."""

    async def close(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()
