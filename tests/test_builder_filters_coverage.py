from app.diff.builder import build_file_diff
from app.diff.coverage import Limits, apply_limits
from app.diff.filters import classify_path, detect_language

PATCH = "@@ -1 +1,2 @@\n a\n+b"


def api(**kw):
    base = {"filename": "src/app.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1, "patch": PATCH}
    base.update(kw)
    return base


def test_normal_python_file():
    fd = build_file_diff(api())
    assert fd.language == "python" and fd.reviewable and fd.additions == 1


def test_added_file():
    fd = build_file_diff(api(status="added", patch="@@ -0,0 +1,2 @@\n+a\n+b", additions=2))
    assert fd.status == "added" and fd.reviewable
    assert [ln.new_no for ln in fd.added_lines()] == [1, 2]


def test_removed_file_is_not_reviewed():
    fd = build_file_diff(api(status="removed", patch="@@ -1 +0,0 @@\n-a"))
    assert fd.ignore_reason == "deleted file" and not fd.reviewable


def test_rename_without_patch_is_not_truncated():
    fd = build_file_diff(api(status="renamed", previous_filename="old.py", patch=None, changes=0, additions=0))
    assert fd.old_path == "old.py" and not fd.is_truncated and not fd.reviewable


def test_missing_patch_with_changes_is_flagged_truncated():
    fd = build_file_diff(api(patch=None, changes=900, additions=900))
    assert fd.is_truncated and not fd.reviewable


def test_binary_lockfile_generated_vendored():
    assert classify_path("img/logo.PNG") == "binary file"
    assert classify_path("web/package-lock.json") == "lockfile"
    assert classify_path("static/app.min.js") == "generated file"
    assert classify_path("node_modules/x/index.js") == "vendored or build directory"
    assert classify_path("src/app.py") is None


def test_binary_file_flag_and_windows_paths():
    fd = build_file_diff(api(filename="assets\\logo.png", patch=None))
    assert fd.is_binary and fd.ignore_reason == "binary file"


def test_config_patterns():
    assert classify_path("db/migrations/001.sql", ["migrations/*"]) == "ignored by config"
    assert classify_path("a/b/x.lock", ["*.lock"]) == "ignored by config"


def test_unparseable_patch_sets_parse_error_not_exception():
    fd = build_file_diff(api(patch="this is not a diff"))
    assert fd.parse_error and not fd.reviewable


def test_detect_language():
    assert detect_language("a/b.tsx") == "typescript"
    assert detect_language("Makefile") is None


def test_coverage_reports_every_skip_with_reason():
    files = [
        build_file_diff(api()),
        build_file_diff(api(filename="yarn.lock")),
        build_file_diff(api(filename="big.py", patch=None, changes=5000)),
    ]
    reviewed, cov = apply_limits(files, Limits())
    assert [f.path for f in reviewed] == ["src/app.py"]
    assert cov.skipped_by_reason() == {"lockfile": 1, "diff too large for GitHub to return": 1}


def test_limits_cap_files_and_lines():
    files = [build_file_diff(api(filename=f"f{i}.py")) for i in range(5)]
    reviewed, cov = apply_limits(files, Limits(max_files=3, max_changed_lines=1500))
    assert len(reviewed) == 3 and cov.skipped_by_reason() == {"over file cap": 2}
    big = [build_file_diff(api(filename=f"g{i}.py", additions=800, changes=800)) for i in range(2)]
    reviewed, cov = apply_limits(big, Limits(max_changed_lines=1000))
    assert len(reviewed) == 1 and cov.skipped_by_reason() == {"over changed-lines cap": 1}
