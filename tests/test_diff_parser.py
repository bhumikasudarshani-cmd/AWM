import pytest

from app.diff.parser import parse_patch, split_patch_lines

SIMPLE = "@@ -1,3 +1,4 @@ def foo():\n line1\n-old\n+new\n+added\n line3"


def nums(hunk, kind):
    return [(ln.old_no, ln.new_no) for ln in hunk.lines if ln.kind == kind]


def test_simple_hunk_numbering():
    res = parse_patch(SIMPLE)
    assert not res.warnings
    (h,) = res.hunks
    assert h.section == "def foo():"
    assert [ln.kind for ln in h.lines] == ["ctx", "del", "add", "add", "ctx"]
    assert nums(h, "ctx") == [(1, 1), (3, 4)]
    assert nums(h, "del") == [(2, None)]
    assert nums(h, "add") == [(None, 2), (None, 3)]


def test_header_without_sizes_means_length_one():
    (h,) = parse_patch("@@ -1 +1 @@\n-a\n+b").hunks
    assert (h.old_len, h.new_len) == (1, 1)
    assert not parse_patch("@@ -1 +1 @@\n-a\n+b").warnings


def test_multiple_hunks_keep_their_own_numbers():
    patch = "@@ -1,2 +1,2 @@\n a\n-b\n+c\n@@ -10,2 +12,3 @@\n x\n+y\n z"
    h1, h2 = parse_patch(patch).hunks
    assert nums(h1, "add") == [(None, 2)]
    assert nums(h2, "add") == [(None, 13)]
    assert nums(h2, "ctx") == [(10, 12), (11, 14)]


def test_crlf_is_stripped():
    (h,) = parse_patch("@@ -1,2 +1,2 @@\r\n a\r\n-b\r\n+c\r\n").hunks
    assert [ln.text for ln in h.lines] == ["a", "b", "c"]


def test_unicode_line_separator_does_not_split_a_line():
    (h,) = parse_patch("@@ -1 +1 @@\n-a\n+b\u2028c").hunks
    assert len(h.lines) == 2
    assert h.lines[1].text == "b\u2028c"


def test_zero_length_insertion_u0():
    (h,) = parse_patch("@@ -5,0 +6,2 @@\n+x\n+y").hunks
    assert [ln.new_no for ln in h.lines] == [6, 7]
    assert h.new_range == (6, 7)


def test_zero_length_deletion_u0_has_no_new_lines():
    (h,) = parse_patch("@@ -5,2 +4,0 @@\n-a\n-b").hunks
    assert [ln.old_no for ln in h.lines] == [5, 6]
    assert h.new_range is None


def test_no_newline_marker_is_skipped():
    patch = "@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file"
    (h,) = parse_patch(patch).hunks
    assert [ln.kind for ln in h.lines] == ["del", "add"]


def test_malformed_header_is_skipped_not_fatal():
    patch = "@@ -1 +1 @@\n-a\n+b\n@@ garbage @@\n+zzz\n@@ -10 +10 @@\n-c\n+d"
    res = parse_patch(patch)
    assert len(res.hunks) == 2
    assert any("malformed" in w for w in res.warnings)
    assert all(ln.text != "zzz" for h in res.hunks for ln in h.lines)


def test_metadata_before_first_hunk_is_ignored():
    res = parse_patch("--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+b")
    assert len(res.hunks) == 1 and len(res.hunks[0].lines) == 2


def test_blank_line_counts_as_context_only_while_hunk_expects_lines():
    (h,) = parse_patch("@@ -1,3 +1,3 @@\n a\n\n-b\n+c").hunks
    assert [ln.kind for ln in h.lines] == ["ctx", "ctx", "del", "add"]
    (h2,) = parse_patch("@@ -1 +1 @@\n-a\n+b\n\n").hunks
    assert len(h2.lines) == 2


def test_count_mismatch_warns_but_keeps_lines():
    res = parse_patch("@@ -1,5 +1,5 @@\n-a\n+b")
    assert len(res.hunks[0].lines) == 2
    assert any("header says" in w for w in res.warnings)


@pytest.mark.parametrize("value", [None, "", "no hunks here at all"])
def test_empty_or_garbage_gives_no_hunks(value):
    assert parse_patch(value).hunks == []


def test_split_patch_lines_drops_single_trailing_newline():
    assert split_patch_lines("a\nb\n") == ["a", "b"]


def test_cross_check_with_unidiff():
    unidiff = pytest.importorskip("unidiff")
    patch = "@@ -1,3 +1,4 @@\n a\n-b\n+c\n+d\n e\n@@ -20,2 +21,2 @@\n x\n-y\n+z"
    ours = {ln.new_no for h in parse_patch(patch).hunks for ln in h.lines if ln.kind == "add"}
    theirs = set()
    for pf in unidiff.PatchSet(f"--- a/f\n+++ b/f\n{patch}\n"):
        for hunk in pf:
            theirs |= {ln.target_line_no for ln in hunk if ln.is_added}
    assert ours == theirs
