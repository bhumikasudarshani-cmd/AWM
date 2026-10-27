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


# ---------------- lenient scoring: a comment within +-1 line of the label still counts ----------------
from app.eval.score import LENIENT_TOLERANCE  # noqa: E402


def test_off_by_one_is_wrong_in_strict_and_right_in_lenient():
    expected, found = [Expected(6, "security")], [f(5)]
    strict, lenient = score_case(expected, found), score_case(expected, found, tolerance=1)
    assert (strict.tp, strict.fp, strict.fn) == (0, 1, 1)
    assert (lenient.tp, lenient.fp, lenient.fn) == (1, 0, 0)


def test_the_comment_below_the_label_counts_too():
    s = score_case([Expected(6, "security")], [f(7)], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (1, 0, 0)


def test_off_by_two_is_wrong_even_in_lenient():
    s = score_case([Expected(6, "security")], [f(4)], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_lenient_still_needs_the_same_category():
    s = score_case([Expected(6, "security")], [f(5, "bug")], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (0, 1, 1)


def test_one_label_cannot_be_matched_by_two_comments():
    # 5 and 7 are both within 1 of label 6; only one may match. The other is on a different line, so it is a
    # false positive: being near a matched issue does not make a comment a duplicate of it.
    s = score_case([Expected(6, "security")], [f(5, title="A"), f(7, title="B")], tolerance=1)
    assert (s.tp, s.fp, s.fn, s.duplicates, s.comments) == (1, 1, 0, 0, 2)


def test_a_second_comment_on_the_same_line_is_still_a_duplicate_in_lenient():
    s = score_case([Expected(6, "security")], [f(6, title="A"), f(6, title="B")], tolerance=1)
    assert (s.tp, s.fp, s.fn, s.duplicates) == (1, 0, 0, 1)


def test_a_wrong_category_comment_next_to_a_matched_issue_is_a_false_positive_not_a_duplicate():
    # real case v12: breakpoint() on line 6 (maintainability), SSRF on line 7 (security).
    # The model said "security" on both lines. The line 6 comment is about another issue.
    s = score_case([Expected(6, "maintainability"), Expected(7, "security")], [f(7), f(6, "security")], tolerance=1)
    assert (s.tp, s.fp, s.fn, s.duplicates) == (1, 1, 1, 0)


def test_exact_comment_wins_over_a_nearer_in_order_but_off_by_one_comment():
    d = diagnose_case([Expected(6, "security")], [f(5, title="near"), f(6, title="exact")], tolerance=1)
    assert [x.title for x in d.matched_findings] == ["exact"]
    assert [x.title for x in d.unexpected] == ["near"] and d.duplicates == []


def test_a_comment_between_two_labels_takes_only_one_of_them():
    s = score_case([Expected(5, "security"), Expected(7, "security")], [f(6)], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (1, 0, 1)


def test_two_neighbouring_labels_are_each_matched_by_their_own_comment():
    s = score_case([Expected(5, "security"), Expected(6, "security")], [f(6, title="A"), f(5, title="B")], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (2, 0, 0)


def test_lenient_on_a_clean_case_is_still_a_false_positive():
    s = score_case([], [f(1)], tolerance=1)
    assert (s.tp, s.fp, s.fn) == (0, 1, 0)


def test_default_tolerance_is_strict_and_the_lenient_constant_is_one():
    assert score_case([Expected(6, "security")], [f(5)]) == score_case([Expected(6, "security")], [f(5)], tolerance=0)
    assert LENIENT_TOLERANCE == 1


def test_summary_carries_lenient_numbers_next_to_the_strict_ones():
    r = CaseResult("a", False, CaseScore(0, 1, 1, 0, 1), None, 0, 0, 0, lenient=CaseScore(1, 0, 0, 0, 1))
    s = summarize([r])
    assert (s.tp, s.precision, s.recall) == (0, 0.0, 0.0)
    assert (s.lenient_tp, s.lenient_fp, s.lenient_fn) == (1, 0, 0)
    assert (s.lenient_precision, s.lenient_recall, s.lenient_f1) == (1.0, 1.0, 1.0)


def test_lenient_columns_come_after_the_strict_ones_in_the_table():
    r = CaseResult("a", False, CaseScore(0, 1, 1, 0, 1), None, 0, 0, 0, lenient=CaseScore(1, 0, 0, 0, 1))
    table = to_markdown({"rules": summarize([r])})
    head = table.splitlines()[0]
    assert head.index("F1") < head.index("Lenient P") < head.index("Lenient R") < head.index("Lenient F1")
    assert len(table.splitlines()[1].strip("|").split("|")) == len(head.strip("|").split("|"))


def test_without_lenient_scores_the_lenient_metrics_are_none():
    assert summarize([result("a", False, CaseScore(1, 0, 0, 0, 1))]).lenient_f1 is None
