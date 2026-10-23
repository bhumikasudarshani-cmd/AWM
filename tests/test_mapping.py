from app.diff.builder import build_file_diff
from app.diff.mapping import (
    commentable_lines, content_hash, hunk_for_line, is_commentable, nearest_commentable, resolve_location,
)

PATCH = "@@ -1,3 +1,4 @@\n a\n-b\n+c\n+d\n e\n@@ -50,2 +60,3 @@\n x\n+y\n z"


def fd():
    return build_file_diff({"filename": "f.py", "status": "modified", "additions": 3, "deletions": 1, "changes": 4, "patch": PATCH})


def test_commentable_lines_are_head_side_lines_in_the_diff():
    assert commentable_lines(fd()) == frozenset({1, 2, 3, 4, 60, 61, 62})
    assert is_commentable(fd(), 3) and not is_commentable(fd(), 5)


def test_deleted_lines_are_not_commentable_on_the_right_side():
    only_del = build_file_diff({"filename": "f.py", "status": "modified", "changes": 2, "patch": "@@ -5,2 +4,0 @@\n-a\n-b"})
    assert commentable_lines(only_del) == frozenset()


def test_nearest_commentable_within_distance():
    f = fd()
    assert nearest_commentable(f, 5) == 4
    assert nearest_commentable(f, 30) is None
    assert nearest_commentable(f, 3) == 3


def test_hunk_for_line():
    f = fd()
    assert hunk_for_line(f, 2) is f.hunks[0]
    assert hunk_for_line(f, 61) is f.hunks[1]
    assert hunk_for_line(f, 30) is None


def test_resolve_location_single_multi_and_cross_hunk():
    f = fd()
    assert resolve_location(f, 2, 2).line == 2
    loc = resolve_location(f, 2, 4)
    assert (loc.start_line, loc.line) == (2, 4)
    cross = resolve_location(f, 3, 61)  # different hunks: fall back to a single line
    assert cross.start_line is None and cross.line == 3
    assert resolve_location(f, 5, 5).line == 4  # near the diff, snapped
    assert resolve_location(f, 30, 31) is None
    assert resolve_location(f, 4, 2).start_line == 2  # reversed range is fixed


def test_content_hash_is_stable_and_content_sensitive():
    a, b = fd().hunks
    assert content_hash(a) == content_hash(fd().hunks[0])
    assert content_hash(a) != content_hash(b)
