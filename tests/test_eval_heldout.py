"""The held-out set must stay separate from the development cases and well formed."""
from pathlib import Path

from app.eval.cases import CATEGORIES, load_cases

ROOT = Path(__file__).resolve().parent.parent / "app" / "eval"
DEV, HELDOUT = load_cases(ROOT / "cases"), load_cases(ROOT / "heldout")


def test_heldout_set_is_big_enough_and_has_both_kinds_of_case():
    assert len(HELDOUT) >= 16
    assert sum(1 for c in HELDOUT if not c.is_clean) >= 6 and sum(1 for c in HELDOUT if c.is_clean) >= 8


def test_heldout_ids_never_overlap_with_the_development_cases():
    assert not ({c.id for c in HELDOUT} & {c.id for c in DEV})


def test_heldout_files_are_longer_than_the_development_cases_on_average():
    avg = lambda cases: sum(len(c.source.splitlines()) for c in cases) / len(cases)  # noqa: E731
    assert avg(HELDOUT) > 1.8 * avg(DEV)


def test_heldout_labels_are_valid_and_point_at_real_lines():
    for c in HELDOUT:
        lines = c.source.splitlines()
        assert "EXPECT" not in c.source, c.id
        for e in c.expected:
            assert e.category in CATEGORIES and 1 <= e.line <= len(lines), c.id
            assert lines[e.line - 1].strip(), f"{c.id}: label on a blank line"


def test_no_two_labels_share_a_line_and_flows_are_labeled_on_one_line():
    for c in HELDOUT:
        keys = [(e.line, e.category) for e in c.expected]
        assert len(keys) == len(set(keys)), c.id
