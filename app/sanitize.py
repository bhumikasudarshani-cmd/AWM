"""Make text that came from a model safe to post as a GitHub comment.

The model reads code that an attacker may have written, so whatever it writes back is untrusted. What this removes:

* @mentions, which notify people (and teams). The @ becomes a full-width one, so the text still reads the same.
* images (a request to someone else's server, with whatever the model put in the URL) and raw HTML.
* a ```suggestion block, which GitHub turns into a one-click "apply this change" button. It becomes a plain text block.
* a copy of our own <!-- awm-reviewer ... --> marker, anywhere, even inside code.
* invisible characters (zero width, bidi overrides, tag characters) and control characters.
* an open code fence, which would swallow the rest of the comment, including our footer.

Text inside code (`inline`, ``double``, or a fenced block) is left as it is, because GitHub does not notify, load images or
render HTML there. Where it is unclear whether something is code, it is treated as not code, which is the safe side.
Ordinary links are not touched. The function is idempotent: sanitising its own output changes nothing.
"""
from __future__ import annotations

import re
from typing import NamedTuple

FULLWIDTH_AT = "\uff20"
ELLIPSIS = "\u2026"

# Invisible or control characters. Tab and newline are kept; carriage returns are turned into newlines first.
_HIDDEN = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e"
    "\u2060-\u2064\u2066-\u206f\ufeff\U000e0000-\U000e007f]"
)
_SUGGESTION = re.compile(r"^((?:[^\S\n]|>)*(?:`{3,}|~{3,}))[^\S\n]*suggestion", re.IGNORECASE)
_FENCE_OPEN = re.compile(r"^((?:[ ]{0,3}>)*[ ]{0,3})(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^((?:[ ]{0,3}>)*[ ]{0,3})(`{3,}|~{3,})[ \t]*$")
_IMAGE = re.compile(r"!\[[^\]`]*\](?:\([^)`]*\)|\[[^\]`]*\])")
_BANG_BRACKET = re.compile(r"!+(?=\[)")
_MENTION = re.compile(r"@(?=[A-Za-z0-9])")
_HTML_TAG = re.compile(r"<(?=[A-Za-z/!?])")


class _Fence(NamedTuple):
    prefix: str
    char: str
    length: int


def _step(line: str, fence: _Fence | None) -> tuple[bool, _Fence | None]:
    """Feed one line. Returns (this line is code or a fence line, the fence that is open after it)."""
    if fence is not None:
        m = _FENCE_CLOSE.match(line)
        if m and m.group(2)[0] == fence.char and len(m.group(2)) >= fence.length:
            return True, None
        return True, fence
    m = _FENCE_OPEN.match(line)
    if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
        return True, _Fence(m.group(1), m.group(2)[0], len(m.group(2)))
    return False, None


def _segments(line: str) -> list[tuple[str, bool]]:
    """Split a line into (text, is_inline_code) pieces, the way CommonMark finds code spans."""
    out: list[tuple[str, bool]] = []
    buf: list[str] = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\" and i + 1 < n:  # a backslash escapes the next character (not inside code)
            buf.append(line[i:i + 2])
            i += 2
            continue
        if c != "`":
            buf.append(c)
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run = j - i
        k, end = j, -1
        while k < n:  # a code span closes at the next backtick run of exactly the same length
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            if m - k == run:
                end = m
                break
            k = m
        if end < 0:  # never closed: the backticks are ordinary text
            buf.append(line[i:j])
            i = j
            continue
        if buf:
            out.append(("".join(buf), False))
            buf = []
        out.append((line[i:end], True))
        i = end
    if buf:
        out.append(("".join(buf), False))
    return out


def _clean_plain(text: str) -> str:
    text = _IMAGE.sub("[image removed]", text)
    text = _BANG_BRACKET.sub("", text)
    text = _MENTION.sub(FULLWIDTH_AT, text)
    return _HTML_TAG.sub("&lt;", text)


def _clean_line(line: str) -> str:
    return "".join(piece if is_code else _clean_plain(piece) for piece, is_code in _segments(line))


def _clean(text: str) -> str:
    """Clean a whole text: suggestion blocks, then everything outside code."""
    lines: list[str] = []
    fence: _Fence | None = None
    for raw in text.split("\n"):
        line = _SUGGESTION.sub(r"\1text", raw)
        is_code, fence = _step(line, fence)
        lines.append(line if is_code else _clean_line(line))
    return "\n".join(lines)


def _closer(text: str) -> str:
    fence = None
    for line in text.split("\n"):
        _, fence = _step(line, fence)
    return "" if fence is None else "\n" + fence.prefix + fence.char * fence.length


def sanitize_text(text: str, max_len: int) -> str:
    """Return text that is safe to post, at most max_len characters long."""
    if not text or max_len <= 0:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HIDDEN.sub("", text).replace("<!--", "&lt;!--")

    # Cut first, clean after. Cutting can end a code span that was closed in the full text; what was inside it is then
    # plain text, and only cleaning the cut text treats it that way. Cleaning can make text longer ("<" becomes
    # "&lt;"), so the cut is tightened until the cleaned text, its ellipsis and any closing fence fit.
    cut = min(len(text), max_len * 4 + 16)
    truncated = len(text) > cut
    for attempt in range(1000):
        head = _clean(text[:cut]) + (ELLIPSIS if truncated else "")
        closer = _closer(head)
        over = len(head) + len(closer) - max_len
        if over <= 0:
            return head + closer
        if cut <= 0:
            break
        truncated = True
        cut = max(0, cut - max(1, over // 4)) if attempt < 30 else cut // 2
    return ""


def _wrap_code(body: str) -> str:
    """Put body in a code span that its own content cannot close: the fence is longer than any backtick run inside."""
    if not body:
        return ""
    fence = "`" * (max((len(run) for run in re.findall("`+", body)), default=0) + 1)
    pad = " " if body.startswith("`") or body.endswith("`") else ""  # CommonMark strips one space on each side
    return f"{fence}{pad}{body}{pad}{fence}"


def inline_code(text: str, max_len: int = 200) -> str:
    """Render text, for example a file name, as one inline code span on one line, at most max_len characters long.

    File names come from the pull request, so they can contain backticks, newlines and a copy of our marker."""
    text = " ".join(_HIDDEN.sub("", text).split()).replace("<!--", "&lt;!--")
    cut, truncated = len(text), False
    while True:
        wrapped = _wrap_code(text[:cut] + (ELLIPSIS if truncated else ""))
        over = len(wrapped) - max_len
        if over <= 0:
            return wrapped
        if cut <= 0:
            return ""
        truncated = True
        cut = max(0, cut - max(1, over))
