from __future__ import annotations

from dataclasses import dataclass

from app.eval.cases import Expected
from app.pipeline.models import Finding


@dataclass(slots=True)
class Diagnosis:
    missed: list[Expected]
    unexpected: list[Finding]  # comments that match no expectation
    duplicates: list[Finding]  # extra comments on an already matched issue
    matched: int = 0


@dataclass(frozen=True, slots=True)
class CaseScore:
    tp: int  # expected issues that got a comment on the right line and category
    fp: int  # comments that match no expected issue (wrong place, wrong category, or on a clean file)
    fn: int  # expected issues nobody commented on
    duplicates: int  # extra comments on an issue that was already matched (noise, not wrongness)
    comments: int  # everything the author would see


def diagnose_case(expected: list[Expected], findings: list[Finding]) -> Diagnosis:
    remaining = list(expected)
    matched: set[tuple[int, str]] = set()
    d = Diagnosis(missed=[], unexpected=[], duplicates=[])
    for f in findings:
        hit = next((e for e in remaining if e.line == f.line_start and e.category == f.category), None)
        if hit is not None:
            remaining.remove(hit)
            matched.add((hit.line, hit.category))
            d.matched += 1
        elif (f.line_start, f.category) in matched:
            d.duplicates.append(f)
        else:
            d.unexpected.append(f)
    d.missed = remaining
    return d


def score_case(expected: list[Expected], findings: list[Finding]) -> CaseScore:
    d = diagnose_case(expected, findings)
    return CaseScore(tp=d.matched, fp=len(d.unexpected), fn=len(d.missed),
                     duplicates=len(d.duplicates), comments=len(findings))
