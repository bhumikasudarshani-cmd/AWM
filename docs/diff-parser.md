# Diff parser

Input is the `patch` text GitHub returns per file (`GET /pulls/{n}/files`). Output is typed objects:
`FileDiff -> Hunk -> DiffLine(kind, text, old_no, new_no)`.

## Rules
- Pure functions, no I/O. Malformed input becomes `warnings`, never an exception.
- Split on `\n` only (git behaviour); strip a trailing `\r` (CRLF files).
- Lines before the first `@@` header (file metadata) are ignored.
- A `@@` line that is not a valid header makes the parser skip until the next valid header.
- Header sizes are optional (`@@ -1 +1 @@` means length 1).
- Zero-length sides (`-U0`): the header names the line before the change, but no line of that side
  exists, so no shift is needed.
- `\ No newline at end of file` is skipped.
- A blank line inside a hunk counts as context only while the hunk still expects lines.

## Which lines can carry a comment
GitHub accepts inline comments only on head-file lines present in the diff (added or context).
`mapping.commentable_lines()` returns them; `resolve_location()` picks a valid line or returns None,
and the finding then goes into the summary instead of causing a 422.

## Coverage
`coverage.apply_limits()` reports what was reviewed and what was skipped and why (lockfile, binary,
generated, vendored, deleted, patch too large for GitHub, over the file or line cap).
Nothing is skipped silently.
