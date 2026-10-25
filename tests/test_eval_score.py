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


def result(case_id, clean, score, error=None, ms=100, pt=10, ct=5):
    return CaseResult(case_id, clean, score, error, ms, pt, ct)


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


def test_metrics_are_none_when_undefined_and_render_as_dash():
    s = summarize([result("a", True, CaseScore(0, 0, 0, 0, 0))])
    assert s.precision is None and s.recall is None and s.f1 is None
    table = to_markdown({"rules": s})
    assert "| rules |" in table and "-" in table


def test_markdown_table_has_one_row_per_config():
    s = summarize([result("a", False, CaseScore(1, 0, 0, 0, 1))])
    table = to_markdown({"rules": s, "llm": s})
    assert table.count("\n") >= 3 and "| llm |" in table and "Precision" in table
