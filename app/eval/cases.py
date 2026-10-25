"""Labeled test cases. A case is a small Python file; a trailing `# EXPECT: <category>` comment
marks a line where a good reviewer should comment. A file with no marker must get no comments.
The markers are removed before the reviewer sees the code, so they never leak into the prompt."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage
from app.diff.models import FileDiff
from app.pipeline.models import ReviewConfig, ReviewContext

CATEGORIES = frozenset({"security", "bug", "maintainability", "style", "test"})
MARKER = re.compile(r"\s*#\s*EXPECT:\s*([A-Za-z_]+)\s*$")


@dataclass(frozen=True, slots=True)
class Expected:
    line: int
    category: str


@dataclass(slots=True)
class Case:
    id: str
    source: str
    expected: list[Expected]

    @property
    def path(self) -> str:
        return f"{self.id}.py"

    @property
    def is_clean(self) -> bool:
        return not self.expected


def parse_case(case_id: str, text: str) -> Case:
    lines: list[str] = []
    expected: list[Expected] = []
    for number, line in enumerate(text.splitlines(), 1):
        m = MARKER.search(line)
        if m:
            category = m.group(1).lower()
            if category not in CATEGORIES:
                raise ValueError(f"{case_id}:{number}: unknown category {m.group(1)!r}")
            expected.append(Expected(number, category))
            line = line[: m.start()]
        lines.append(line)
    return Case(case_id, "\n".join(lines) + "\n", expected)


def load_cases(directory: str | Path) -> list[Case]:
    return [parse_case(p.stem, p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("*.py"))]


def case_to_file_diff(case: Case) -> FileDiff:
    lines = case.source.splitlines()
    patch = f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + ln for ln in lines)
    return build_file_diff({
        "filename": case.path, "status": "added",
        "additions": len(lines), "deletions": 0, "changes": len(lines), "patch": patch,
    })


def case_context(case: Case, cfg: ReviewConfig | None = None) -> ReviewContext:
    fd = case_to_file_diff(case)
    return ReviewContext(
        repo="eval/cases", number=1, head_sha="0" * 40, title=case.id, body="", author="eval",
        files=[fd], coverage=Coverage(reviewed=[fd.path]), config=cfg or ReviewConfig(),
    )
