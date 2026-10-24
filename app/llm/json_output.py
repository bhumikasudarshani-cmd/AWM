"""Turn model text into validated findings. Models wrap JSON in prose and fences, so be forgiving
about the wrapper and strict about the content."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.llm.base import LLMOutputError, LLMProvider, LLMResponse
from app.pipeline.models import Severity

RETRY_HINT = (
    "\n\nYour previous reply was not valid JSON for the required schema. "
    "Reply again with ONLY the JSON object."
)


class RawLLMFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str = Field(min_length=1, max_length=200)
    explanation: str = ""
    suggested_fix: str | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def _severity(cls, v: Any) -> Any:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence(cls, v: Any) -> Any:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return v
        return x / 100 if 1 < x <= 100 else x  # some models answer 85 instead of 0.85

    @field_validator("explanation", mode="before")
    @classmethod
    def _explanation(cls, v: Any) -> Any:
        return "" if v is None else v


def extract_json_object(text: str) -> dict:
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    s = s.strip()

    try:
        whole = json.loads(s)
        if isinstance(whole, dict):
            return whole
        if isinstance(whole, list):
            return {"findings": whole}
    except ValueError:
        pass

    decoder = json.JSONDecoder()
    pos = s.find("{")
    while pos != -1:
        try:
            obj, _ = decoder.raw_decode(s, pos)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        pos = s.find("{", pos + 1)
    raise LLMOutputError("no JSON object found in the model reply")


def parse_llm_findings(text: str) -> tuple[list[RawLLMFinding], int]:
    """Return (valid findings, number of invalid items dropped)."""
    items = extract_json_object(text).get("findings")
    if not isinstance(items, list):
        raise LLMOutputError("reply has no 'findings' list")
    valid: list[RawLLMFinding] = []
    bad = 0
    for item in items:
        try:
            valid.append(RawLLMFinding.model_validate(item))
        except ValidationError:
            bad += 1
    return valid, bad


async def complete_findings(
    provider: LLMProvider, system: str, user: str, retries: int = 1
) -> tuple[list[RawLLMFinding], int, list[LLMResponse]]:
    """Ask for findings; if the reply is unusable, ask again (up to `retries` times)."""
    responses: list[LLMResponse] = []
    hint = ""
    last: LLMOutputError | None = None
    for _ in range(retries + 1):
        resp = await provider.complete(system, user + hint)  # transport errors propagate: not retried here
        responses.append(resp)
        try:
            valid, bad = parse_llm_findings(resp.text)
            return valid, bad, responses
        except LLMOutputError as exc:
            last, hint = exc, RETRY_HINT
    assert last is not None
    raise last
