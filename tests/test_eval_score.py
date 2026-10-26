import pytest

from app.eval.cases import Expected
from app.eval.report import CaseResult, summarize, to_markdown
from app.eval.score import CaseScore, score_case
from app.pipeline.models import Finding


def f(line, category="security", title="T"):
    return Finding(file="x.py", line_start=line, line_end=line, category=category, severity="high",
                   confidence=0.9, title=title)


def test_perfect_match():
    assert score_case([Expected(3, "security")], [f(3)]) == CaseScore(tp=1, fp=0, fn=0, duplicates=0, comments=1)


def test_miss_and_wrong_location_are_counted_separately():
    s = score_case([Expected(3, "security")], [f(9)])
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_wrong_category_is_both_a_false_positive_and_a_miss():
    s = score_case([Expected(3, "maintainability")], [f(3, "security")])
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_second_comment_on_an_already_matched_line_is_a_duplicate_not_a_false_positive():
    s = score_case([Expected(3, "security")], [f(3, title="A"), f(3, title="B")])
    assert (s.tp, s.fp, s.fn, s.duplicates, s.comments) == (1, 0, 0, 1, 2)


def test_any_comment_on_a_clean_case_is_a_false_positive():
    s = score_case([], [f(1)])
    assert (s.tp, s.fp, s.fn) == (0, 1, 0)


def result(case_id, clean, score, error=None, ms=100, pt=10, ct=5, held=0):
    return CaseResult(case_id, clean, score, error, ms, pt, ct, held_back=held)


def test_summary_metrics_and_false_alarms():
    results = [
        result("a", False, CaseScore(2, 0, 0, 0, 2)),
        result("b", False, CaseScore(1, 1, 1, 1, 3)),
        result("c", True, CaseScore(0, 1, 0, 0, 1)),
        result("d", True, CaseScore(0, 0, 0, 0, 0), error="boom"),
    ]
    s = summarize(results)
    assert (s.cases, s.clean_cases, s.false_alarm_cases, s.errors) == (4, 2, 1, 1)
    assert s.precision == pytest.approx(3 / 5) and s.recall == pytest.approx(3 / 4)
    assert s.f1 == pytest.approx(2 * 0.6 * 0.75 / (0.6 + 0.75))
    assert s.comments_per_case == pytest.approx(6 / 4) and s.duplicates == 1
    assert (s.prompt_tokens, s.completion_tokens, s.duration_ms) == (40, 20, 400)
    assert summarize([result("a", False, CaseScore(1, 0, 0, 0, 1), held=3), result("b", True, CaseScore(0, 0, 0, 0, 0), held=2)]).held_back == 5


def test_metrics_are_none_when_undefined_and_render_as_dash():
    s = summarize([result("a", True, CaseScore(0, 0, 0, 0, 0))])
    assert s.precision is None and s.recall is None and s.f1 is None
    table = to_markdown({"rules": s})
    assert "| rules |" in table and "-" in table


def test_markdown_table_has_one_row_per_config():
    s = summarize([result("a", False, CaseScore(1, 0, 0, 0, 1))])
    table = to_markdown({"rules": s, "llm": s})
    assert table.count("\n") >= 3 and "| llm |" in table and "Precision" in table


# ---------------- diagnosis: which expectations were missed, which comments were wrong ----------------
from app.eval.score import diagnose_case  # noqa: E402


def test_diagnosis_lists_misses_unexpected_comments_and_duplicates():
    d = diagnose_case([Expected(3, "security"), Expected(8, "security")],
                      [f(3, title="A"), f(3, title="B"), f(20, title="C")])
    assert [e.line for e in d.missed] == [8]
    assert [x.title for x in d.unexpected] == ["C"]
    assert [x.title for x in d.duplicates] == ["B"]


def test_diagnosis_of_a_perfect_case_is_empty():
    d = diagnose_case([Expected(3, "security")], [f(3)])
    assert d.missed == [] and d.unexpected == [] and d.duplicates == []


# ---------------- confidence calibration ----------------
from app.eval.report import confidence_sweep, format_sweep  # noqa: E402


def test_diagnosis_keeps_the_matched_findings_so_their_confidence_can_be_studied():
    d = diagnose_case([Expected(3, "security")], [f(3), f(9)])
    assert [x.line_start for x in d.matched_findings] == [3] and [x.line_start for x in d.unexpected] == [9]


def marked(case_id, marks, tp, fn):
    return CaseResult(case_id, False, CaseScore(tp, len(marks) - tp, fn, 0, len(marks)), None, 0, 0, 0, marks=marks)


def test_sweep_shows_what_a_higher_confidence_threshold_would_do():
    results = [marked("a", [(0.9, True), (0.8, True), (0.6, False), (0.55, False)], tp=2, fn=1)]
    rows = {t: (p, r, n) for t, p, r, n in confidence_sweep(results, thresholds=(0.5, 0.7, 0.95))}
    assert rows[0.5] == (0.5, pytest.approx(2 / 3), 4)
    assert rows[0.7] == (1.0, pytest.approx(2 / 3), 2)
    assert rows[0.95] == (None, 0.0, 0)


def test_sweep_text_lists_each_config_and_skips_configs_without_comments():
    results = {"llm": [marked("a", [(0.9, True)], tp=1, fn=0)], "rules": [marked("b", [], tp=0, fn=1)]}
    text = format_sweep(results)
    assert "llm" in text and ">=0.9" in text and "rules" not in text


def test_summary_reports_average_confidence_of_correct_and_wrong_comments():
    s = summarize([marked("a", [(0.9, True), (0.8, True), (0.6, False)], tp=2, fn=0)])
    assert s.mean_conf_correct == pytest.approx(0.85) and s.mean_conf_wrong == pytest.approx(0.6)
    assert summarize([marked("b", [], tp=0, fn=0)]).mean_conf_correct is None
