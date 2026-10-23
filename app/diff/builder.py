"""Turn one GitHub 'list pull request files' item into a FileDiff."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.diff.filters import classify_path, detect_language
from app.diff.models import FileDiff
from app.diff.parser import parse_patch

STATUS_MAP = {
    "added": "added", "removed": "removed", "modified": "modified", "renamed": "renamed",
    "copied": "copied", "changed": "modified", "unchanged": "unchanged",
}


def build_file_diff(api_file: dict[str, Any], extra_ignore: Iterable[str] = ()) -> FileDiff:
    path = str(api_file.get("filename", ""))
    fd = FileDiff(
        path=path,
        status=STATUS_MAP.get(str(api_file.get("status")), "modified"),
        old_path=api_file.get("previous_filename"),
        language=detect_language(path),
        additions=int(api_file.get("additions") or 0),
        deletions=int(api_file.get("deletions") or 0),
    )

    reason = classify_path(path, extra_ignore)
    if reason:
        fd.ignore_reason = reason
        fd.is_binary = reason == "binary file"
        return fd
    if fd.status == "removed":
        fd.ignore_reason = "deleted file"
        return fd

    patch = api_file.get("patch")
    if not patch:
        # GitHub omits `patch` for very large diffs; a pure rename also has none.
        changes = int(api_file.get("changes") or (fd.additions + fd.deletions))
        fd.is_truncated = changes > 0
        return fd

    try:
        parsed = parse_patch(patch)
    except Exception as exc:  # the parser should not raise, but one file must never kill a review
        fd.parse_error = f"{type(exc).__name__}: {exc}"
        return fd

    fd.hunks, fd.warnings = parsed.hunks, parsed.warnings
    if not fd.hunks:
        fd.parse_error = "no hunks found in patch"
    return fd
