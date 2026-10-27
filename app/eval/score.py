from __future__ import annotations

from dataclasses import dataclass, field

from app.eval.cases import Expected
from app.pipeline.models import Finding


@dataclass(slots=True)
class Diagnosis:
    missed: list[Expected]
    unexpected: list[Finding]  # comments that match no expectation
    duplicates: list[Finding]  # extra comments on an already matched issue
    matched: int = 0
    matched_findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CaseScore:
    tp: int  # expected issues that got a comment on the right line and category
    fp: int  # comments that match no expected issue (wrong place, wrong category, or on a clean file)
    fn: int  # expected issues nobody commented on
    duplicates: int  # extra comments on an issue that was already matched (noise, not wrongness)
    comments: int  # everything the author would see


LENIENT_TOLERANCE = 1  # lenient scoring accepts a comment up to this many lines away from the labeled line


def diagnose_case(expected: list[Expected], findings: list[Finding], tolerance: int = 0) -> Diagnosis:
    """Match comments to expected issues one to one. tolerance=0 is strict (same line); tolerance=1 also accepts
    a comment one line above or below. The closest pairs are matched first, so an exact comment always beats a
    near one, whatever order the comments arrive in. A comment that matches nothing is a duplicate only if it sits on
    the very line of an already matched issue (same category); a neighbouring line may be a different issue, so
    that is a false positive, even in lenient mode."""
    pairs = sorted(
        (abs(f.line_start - e.line), fi, ei)
        for fi, f in enumerate(findings)
        for ei, e in enumerate(expected)
        if e.category == f.category and abs(f.line_start - e.line) <= tolerance
    )
    used_f: set[int] = set()
    used_e: set[int] = set()
    for _, fi, ei in pairs:
        if fi not in used_f and ei not in used_e:
            used_f.add(fi)
            used_e.add(ei)
    matched = [expected[ei] for ei in sorted(used_e)]
    d = Diagnosis(missed=[e for ei, e in enumerate(expected) if ei not in used_e], unexpected=[], duplicates=[],
                  matched=len(used_f))
    for fi, f in enumerate(findings):
        if fi in used_f:
            d.matched_findings.append(f)
        elif any(m.category == f.category and f.line_start == m.line for m in matched):
            d.duplicates.append(f)
        else:
            d.unexpected.append(f)
    return d


def score_case(expected: list[Expected], findings: list[Finding], tolerance: int = 0) -> CaseScore:
    d = diagnose_case(expected, findings, tolerance)
    return CaseScore(tp=d.matched, fp=len(d.unexpected), fn=len(d.missed),
                     duplicates=len(d.duplicates), comments=len(findings))
