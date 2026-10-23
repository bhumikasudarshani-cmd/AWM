from __future__ import annotations

from typing import Protocol

from app.pipeline.models import Finding, ReviewContext


class Stage(Protocol):
    """A pipeline stage turns a ReviewContext into candidate findings.

    Every stage (rules, security LLM, bugs LLM, ...) implements this one interface,
    so stages can be added, swapped or switched off per repository, and evaluated
    on their own.
    """

    name: str

    async def run(self, ctx: ReviewContext) -> list[Finding]: ...
