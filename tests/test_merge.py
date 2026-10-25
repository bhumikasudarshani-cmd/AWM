"""Findings at the same place are one issue: merge them, keep every source as evidence."""
import asyncio

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage
from app.pipeline.models import Evidence, Finding, ReviewConfig, ReviewContext
from app.pipeline.runner import merge_findings, run_pipeline


def f(line=2, category="security", severity="medium", confidence=0.6, title="T", tool="rules", rule="r",
      fix=None, anchor="x = 1", line_end=None, explanation=""):
    return Finding(file="a.py", line_start=line, line_end=line_end or line, category=category, severity=severity,
                   confidence=confidence, title=title, suggested_fix=fix, explanation=explanation,
                   evidence=[Evidence(tool=tool, rule=rule)], anchor_text=anchor)


def test_same_line_and_category_become_one_finding_with_both_sources():
    (m,) = merge_findings([f(title="Shell injection", tool="llm", confidence=0.8, severity="high"),
                           f(title="subprocess with shell=True", tool="rules", confidence=0.65)])
    assert m.title == "Shell injection" and m.severity == "high" and m.confidence == 0.8
    assert [(e.tool, e.rule) for e in m.evidence] == [("llm", "r"), ("rules", "r")]
    assert m.tools == {"llm", "rules"}


def test_the_more_confident_finding_provides_the_wording_and_the_highest_severity_wins():
    (m,) = merge_findings([f(severity="high", confidence=0.5, title="rules title", explanation="short"),
                           f(severity="low", confidence=0.9, title="model title", explanation="long", tool="llm")])
    assert m.title == "model title" and m.explanation == "long" and m.severity == "high"


def test_a_missing_suggested_fix_is_taken_from_the_other_finding():
    (m,) = merge_findings([f(confidence=0.9, fix=None, tool="llm"), f(confidence=0.5, fix="Use a list.")])
    assert m.suggested_fix == "Use a list."


def test_different_category_or_different_line_stays_separate():
    out = merge_findings([f(line=2), f(line=2, category="maintainability"), f(line=3)])
    assert len(out) == 3


def test_duplicate_evidence_is_not_repeated_and_the_line_range_widens():
    (m,) = merge_findings([f(line_end=4, tool="llm", confidence=0.9), f(line_end=2, tool="llm", confidence=0.5)])
    assert len(m.evidence) == 1 and (m.line_start, m.line_end) == (2, 4)


def test_fingerprint_does_not_change_when_only_the_title_changes():
    assert f(title="Command injection via shell=True").fingerprint == f(title="Insecure use of shell=True").fingerprint
    assert f(category="bug").fingerprint != f(category="security").fingerprint
    assert f(anchor="y = 2").fingerprint != f(anchor="x = 1").fingerprint


class Fixed:
    def __init__(self, name, findings):
        self.name, self._f = name, findings

    async def run(self, ctx):
        return self._f


def ctx():
    fd = build_file_diff({"filename": "a.py", "status": "modified", "changes": 2, "additions": 2,
                          "patch": "@@ -1 +1,3 @@\n a\n+b\n+c"})
    return ReviewContext("o/r", 1, "abc1234", "t", "", "me", [fd], Coverage(reviewed=["a.py"]), ReviewConfig())


def test_pipeline_merges_what_different_stages_found_at_the_same_place():
    res = asyncio.run(run_pipeline(ctx(), [Fixed("rules", [f(tool="rules", title="A")]),
                                           Fixed("llm", [f(tool="llm", title="B", confidence=0.9)])]))
    (m,) = res.findings
    assert m.title == "B" and m.tools == {"rules", "llm"}
