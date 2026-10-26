"""A weak rule match in a category the AI review covers is held back unless the AI confirmed it."""
import asyncio

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage, SkippedFile
from app.llm.base import LLMError
from app.pipeline.models import Evidence, Finding, ReviewConfig, ReviewContext
from app.pipeline.runner import run_pipeline
from app.pipeline.stages.rules import RulesStage
from app.pipeline.stages.security_llm import LLMSecurityStage
from tests.fakes import FakeProvider

PATCH = "@@ -1 +1,3 @@\n a\n+b = eval(x)\n+c = 2"


class Stage:
    def __init__(self, name, findings, covers=None, error=None):
        self.name, self._f, self._error = name, findings, error
        if covers:
            self.covers = frozenset(covers)

    async def run(self, ctx):
        if self._error:
            raise self._error
        return self._f


def finding(line=2, category="security", confidence=0.6, tool="rules", file="a.py"):
    return Finding(file=file, line_start=line, line_end=line, category=category, severity="medium",
                   confidence=confidence, title="T", evidence=[Evidence(tool=tool)], anchor_text=f"line {line}")


def ctx(partial=(), cfg=None):
    fd = build_file_diff({"filename": "a.py", "status": "modified", "changes": 2, "additions": 2, "patch": PATCH})
    cov = Coverage(reviewed=["a.py"], partial=[SkippedFile(p, "skipped") for p in partial])
    return ReviewContext("o/r", 1, "abc1234", "t", "", "me", [fd], cov, cfg or ReviewConfig())


def run(c, stages):
    return asyncio.run(run_pipeline(c, stages))


def test_unconfirmed_weak_rule_match_is_held_back_and_reported():
    res = run(ctx(), [Stage("rules", [finding()]), Stage("llm-security", [], covers={"security"})])
    assert res.findings == [] and [f.line_start for f in res.suppressed] == [2]


def test_a_rule_match_the_ai_also_flagged_is_kept_as_one_merged_finding():
    res = run(ctx(), [Stage("rules", [finding()]),
                      Stage("llm-security", [finding(tool="llm", confidence=0.8)], covers={"security"})])
    (f,) = res.findings
    assert f.tools == {"rules", "llm"} and res.suppressed == []


def test_a_very_confident_rule_match_is_never_held_back():
    res = run(ctx(), [Stage("rules", [finding(confidence=0.95)]), Stage("llm-security", [], covers={"security"})])
    assert len(res.findings) == 1


def test_nothing_is_held_back_when_the_ai_stage_failed():
    res = run(ctx(), [Stage("rules", [finding()]),
                      Stage("llm-security", [], covers={"security"}, error=LLMError("down"))])
    assert len(res.findings) == 1 and res.suppressed == []


def test_nothing_is_held_back_for_a_file_the_ai_did_not_fully_review():
    res = run(ctx(partial=["a.py"]), [Stage("rules", [finding()]), Stage("llm-security", [], covers={"security"})])
    assert len(res.findings) == 1


def test_categories_the_ai_does_not_cover_pass_through():
    res = run(ctx(), [Stage("rules", [finding(category="maintainability")]),
                      Stage("llm-security", [], covers={"security"})])
    assert len(res.findings) == 1


def test_without_a_covering_stage_nothing_is_held_back():
    assert len(run(ctx(), [Stage("rules", [finding()])]).findings) == 1


def test_the_gate_can_be_switched_off():
    c = ctx(cfg=ReviewConfig(require_corroboration=False))
    res = run(c, [Stage("rules", [finding()]), Stage("llm-security", [], covers={"security"})])
    assert len(res.findings) == 1 and res.suppressed == []


def test_the_ai_stages_own_findings_are_never_held_back():
    res = run(ctx(), [Stage("llm-security", [finding(tool="llm", confidence=0.55)], covers={"security"})])
    assert len(res.findings) == 1


def test_stage_declarations():
    assert LLMSecurityStage(FakeProvider(["{}"])).covers == frozenset({"security"})
    assert not getattr(RulesStage(), "covers", None)


def test_files_in_a_failed_model_batch_are_recorded_as_not_fully_reviewed():
    fd = build_file_diff({"filename": "a.py", "status": "modified", "changes": 2, "patch": PATCH})
    c = ReviewContext("o/r", 1, "abc1234", "t", "", "me", [fd], Coverage(reviewed=["a.py"]), ReviewConfig())
    stage = LLMSecurityStage(FakeProvider([LLMError("down")]), retries=0)
    try:
        asyncio.run(stage.run(c))
    except LLMError:
        pass
    assert [(s.path, s.reason) for s in c.coverage.partial] == [("a.py", "AI security review failed for this file")]


def test_an_ai_finding_of_another_category_on_the_same_line_does_not_confirm_a_security_match():
    ai_bug = finding(category="bug", tool="llm", confidence=0.8)
    res = run(ctx(), [Stage("rules", [finding()]), Stage("llm-security", [ai_bug], covers={"security"})])
    assert [f.category for f in res.findings] == ["bug"] and len(res.suppressed) == 1
