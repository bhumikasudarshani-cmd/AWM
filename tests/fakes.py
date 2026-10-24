"""Test doubles shared by the LLM tests."""
from app.llm.base import LLMResponse


class FakeProvider:
    """Returns scripted replies in order (the last one repeats). An Exception reply is raised."""

    def __init__(self, replies, model="fake-model"):
        self.model = model
        self._replies = list(replies)
        self.calls: list[dict] = []
        self.closed = False

    async def complete(self, system, user, *, json_mode=True):
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(text=reply, model=self.model, prompt_tokens=len(user) // 4,
                           completion_tokens=10, latency_ms=1)

    async def aclose(self):
        self.closed = True
