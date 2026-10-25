from pathlib import Path

import pytest

from app.diff.mapping import commentable_lines
from app.eval.cases import CATEGORIES, Expected, case_context, case_to_file_diff, load_cases, parse_case

CASES_DIR = Path(__file__).resolve().parent.parent / "app" / "eval" / "cases"


def test_parse_case_strips_markers_and_records_line_numbers():
    case = parse_case("x", "a = 1\nb = eval(s)  # EXPECT: security\nc = 3\n")
    assert case.expected == [Expected(2, "security")]
    assert case.source == "a = 1\nb = eval(s)\nc = 3\n" and not case.is_clean


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError):
        parse_case("x", "a = 1  # EXPECT: banana\n")


def test_case_without_markers_is_clean_and_unchanged():
    case = parse_case("x", "a = 1\nb = 2\n")
    assert case.is_clean and case.source == "a = 1\nb = 2\n"


def test_marker_must_be_a_trailing_comment():
    case = parse_case("x", 'msg = "# EXPECT: security is a label"\n')
    assert case.is_clean


def test_case_becomes_an_added_file_diff_without_marker_text():
    case = parse_case("demo", "a = 1\nb = eval(s)  # EXPECT: security\n")
    fd = case_to_file_diff(case)
    assert fd.path == "demo.py" and fd.reviewable and fd.language == "python"
    assert commentable_lines(fd) == frozenset({1, 2})
    assert all("EXPECT" not in ln.text for ln in fd.added_lines())


def test_case_context_holds_one_reviewable_file():
    ctx = case_context(parse_case("demo", "a = 1\n"))
    assert [f.path for f in ctx.files] == ["demo.py"] and ctx.coverage.reviewed == ["demo.py"]


def test_the_real_dataset_is_well_formed():
    cases = load_cases(CASES_DIR)
    assert len(cases) >= 20 and len({c.id for c in cases}) == len(cases)
    assert sum(1 for c in cases if not c.is_clean) >= 10 and sum(1 for c in cases if c.is_clean) >= 10
    for c in cases:
        n = len(c.source.splitlines())
        assert "EXPECT" not in c.source, c.id
        for e in c.expected:
            assert e.category in CATEGORIES and 1 <= e.line <= n, c.id
            assert c.source.splitlines()[e.line - 1].strip(), f"{c.id}: expected line {e.line} is blank"
