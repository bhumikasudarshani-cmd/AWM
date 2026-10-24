from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """The model call failed (network, timeout, HTTP error). Messages never contain the prompt."""


class LLMOutputError(LLMError):
    """The model answered, but not in a usable shape."""


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


class LLMProvider(Protocol):
    model: str

    async def complete(self, system: str, user: str, *, json_mode: bool = True) -> LLMResponse: ...
