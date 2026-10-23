import asyncio

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage
from app.pipeline.models import Evidence, Finding, ReviewConfig, ReviewContext
from app.pipeline.runner import run_pipeline, select_findings
from app.pipeline.stages.rules import RulesStage

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"  # built at runtime so the repo never contains a key-shaped literal


def make_ctx(filename, patch, **cfg):
    fd = build_file_diff({"filename": filename, "status": "modified", "additions": 5, "changes": 5, "patch": patch})
    return ReviewContext("o/r", 1, "abc1234def", "t", "", "me", [fd], Coverage(reviewed=[fd.path]), ReviewConfig(**cfg))


def run(coro):
    return asyncio.run(coro)


def test_rules_flag_added_lines_only():
    ctx = make_ctx("a.py", f'@@ -1,2 +1,3 @@\n x = "{AWS}"\n-eval(old)\n+eval(new)\n z')
    titles = {f.title: f for f in run(RulesStage().run(ctx))}
    assert "AWS access key ID in source" not in titles          # context line, not added
    assert titles["Dynamic code evaluation"].line_start == 2    # only the added eval, not the deleted one


def test_aws_key_detected_with_line_number_and_evidence():
    ctx = make_ctx("a.py", f'@@ -1 +1,2 @@\n a\n+key = "{AWS}"')
    (f,) = [x for x in run(RulesStage().run(ctx)) if x.severity == "critical"]
    assert f.line_start == 2 and f.evidence == [Evidence(tool="rules", rule="aws-access-key")]


def test_placeholder_secrets_and_literal_eval_are_not_flagged():
    patch = '@@ -1 +1,3 @@\n a\n+password = "your_password_here"\n+ast.literal_eval(x)'
    assert run(RulesStage().run(make_ctx("a.py", patch))) == []


def test_real_looking_password_is_flagged():
    patch = '@@ -1 +1,2 @@\n a\n+password = "hunter2hunter2"'
    (f,) = run(RulesStage().run(make_ctx("a.py", patch)))
    assert f.category == "security" and "hunter2" not in f.explanation


def test_language_specific_rules():
    js = make_ctx("a.js", "@@ -1 +1,2 @@\n a\n+debugger;")
    py = make_ctx("a.py", "@@ -1 +1,2 @@\n a\n+debugger;")
    assert len(run(RulesStage().run(js))) == 1
    assert run(RulesStage().run(py)) == []


class Boom:
    name = "boom"

    async def run(self, ctx):
        raise RuntimeError("model unavailable")


class Fixed:
    name = "fixed"

    def __init__(self, findings):
        self._f = findings

    async def run(self, ctx):
        return self._f


def finding(**kw):
    base = dict(file="a.py", line_start=2, line_end=2, category="security", severity="high",
                confidence=0.8, title="T", anchor_text="x")
    base.update(kw)
    return Finding(**base)


def test_failing_stage_is_isolated_and_reported():
    ctx = make_ctx("a.py", "@@ -1 +1,2 @@\n a\n+b")
    res = run(run_pipeline(ctx, [Boom(), Fixed([finding()])]))
    assert len(res.findings) == 1
    errors = {r.stage: r.error for r in res.stage_results}
    assert errors["boom"].startswith("RuntimeError") and errors["fixed"] is None


def test_pipeline_dedupes_keeps_highest_confidence_and_merges_evidence():
    ctx = make_ctx("a.py", "@@ -1 +1,2 @@\n a\n+b")
    a = finding(confidence=0.6, evidence=[Evidence(tool="rules", rule="r1")])
    b = finding(confidence=0.9, evidence=[Evidence(tool="llm")])
    res = run(run_pipeline(ctx, [Fixed([a]), Fixed([b])]))
    (f,) = res.findings
    assert f.confidence == 0.9 and {e.tool for e in f.evidence} == {"rules", "llm"}


def test_findings_for_unknown_files_are_dropped():
    ctx = make_ctx("a.py", "@@ -1 +1,2 @@\n a\n+b")
    res = run(run_pipeline(ctx, [Fixed([finding(file="ghost.py")])]))
    assert res.findings == [] and res.dropped_unknown_file == 1


def test_select_applies_thresholds_and_cap_in_priority_order():
    fs = [finding(title=f"T{i}", confidence=0.9 - i * 0.01, line_start=i + 1, line_end=i + 1) for i in range(5)]
    fs.append(finding(title="weak", confidence=0.2))
    fs.append(finding(title="crit", severity="critical", confidence=0.6, line_start=50, line_end=50))
    sel = select_findings(fs, ReviewConfig(max_comments=3, min_confidence=0.5))
    assert sel.selected[0].title == "crit"
    assert len(sel.selected) == 3 and len(sel.overflow) == 3 and sel.below_threshold == 1


def test_finding_fingerprint_ignores_line_shift_when_anchor_present():
    assert finding(line_start=2, line_end=2).fingerprint == finding(line_start=40, line_end=40).fingerprint
    assert finding(anchor_text="y").fingerprint != finding().fingerprint


def test_finding_swaps_reversed_lines():
    f = finding(line_start=9, line_end=3)
    assert (f.line_start, f.line_end) == (3, 9)
