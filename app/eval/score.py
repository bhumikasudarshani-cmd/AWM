from __future__ import annotations

from dataclasses import dataclass

from app.eval.cases import Expected
from app.pipeline.models import Finding


@dataclass(frozen=True, slots=True)
class CaseScore:
    tp: int  # expected issues that got a comment on the right line and category
    fp: int  # comments that match no expected issue (wrong place, wrong category, or on a clean file)
    fn: int  # expected issues nobody commented on
    duplicates: int  # extra comments on an issue that was already matched (noise, not wrongness)
    comments: int  # everything the author would see


def score_case(expected: list[Expected], findings: list[Finding]) -> CaseScore:
    remaining = list(expected)
    matched: set[tuple[int, str]] = set()
    tp = fp = dup = 0
    for f in findings:
        hit = next((e for e in remaining if e.line == f.line_start and e.category == f.category), None)
        if hit is not None:
            remaining.remove(hit)
            matched.add((hit.line, hit.category))
            tp += 1
        elif (f.line_start, f.category) in matched:
            dup += 1
        else:
            fp += 1
    return CaseScore(tp=tp, fp=fp, fn=len(remaining), duplicates=dup, comments=len(findings))
