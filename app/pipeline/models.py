from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.diff.coverage import Coverage, Limits
from app.diff.models import FileDiff

Category = Literal["security", "bug", "maintainability", "style", "test"]
Severity = Literal["low", "medium", "high", "critical"]
SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Evidence(BaseModel):
    tool: str
    rule: str | None = None
    ref: str | None = None


class Finding(BaseModel):
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str = Field(min_length=1, max_length=200)
    explanation: str = ""
    suggested_fix: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    source_stage: str = "unknown"
    anchor_text: str | None = None  # the flagged source line; keeps the fingerprint stable across pushes

    @model_validator(mode="after")
    def _order_lines(self) -> Finding:
        if self.line_end < self.line_start:
            self.line_start, self.line_end = self.line_end, self.line_start
        return self

    @property
    def fingerprint(self) -> str:
        basis = f"{self.file}|{self.category}|{self.title}|{self.anchor_text or self.line_start}"
        return hashlib.sha1(basis.encode()).hexdigest()[:16]


@dataclass(slots=True)
class ReviewConfig:
    min_severity: Severity = "low"
    min_confidence: float = 0.5
    max_comments: int = 12
    ignore_paths: tuple[str, ...] = ()
    limits: Limits = field(default_factory=Limits)
    post_when_clean: bool = True


@dataclass(slots=True)
class ReviewContext:
    repo: str
    number: int
    head_sha: str
    title: str
    body: str
    author: str
    files: list[FileDiff]
    coverage: Coverage
    config: ReviewConfig = field(default_factory=ReviewConfig)

    def files_by_path(self) -> dict[str, FileDiff]:
        return {f.path: f for f in self.files}


@dataclass(slots=True)
class StageResult:
    stage: str
    findings: list[Finding]
    duration_ms: int
    error: str | None = None
