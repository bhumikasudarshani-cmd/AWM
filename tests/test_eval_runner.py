import asyncio
import json

from app.eval.cases import parse_case
from app.eval.provider import CachingProvider
from app.eval.runner import evaluate, run_configs
from app.llm.base import LLMError
from app.pipeline.stages.rules import RulesStage
from tests.fakes import FakeProvider

BAD = parse_case("bad", "import subprocess\nsubprocess.run(cmd, shell=True)  # EXPECT: security\n")
CLEAN = parse_case("clean", "import subprocess\nsubprocess.run(['ls'])\n")
COMMENT = parse_case("comment", "# do not use eval(x) here\nx = 1\n")


def llm_reply(line):
    return json.dumps({"findings": [{"file": "bad.py", "line": line, "severity": "high", "confidence": 0.8,
                                     "title": "Shell injection", "explanation": "x"}]})


def run(coro):
    return asyncio.run(coro)


def test_rules_baseline_catches_the_bad_case_and_misses_nothing_on_the_clean_one():
    results = run(evaluate([BAD, CLEAN], lambda: [RulesStage()]))
    by_id = {r.case_id: r for r in results}
    assert (by_id["bad"].score.tp, by_id["bad"].score.fp) == (1, 0)
    assert by_id["clean"].score.comments == 0 and by_id["clean"].is_clean


def test_a_noisy_rule_on_a_clean_case_shows_up_as_a_false_alarm():
    (r,) = run(evaluate([COMMENT], lambda: [RulesStage()]))
    assert r.score.fp == 1 and r.is_clean


def test_run_configs_compares_rules_llm_and_both(tmp_path):
    inner = FakeProvider([llm_reply(2)], model="fake")
    provider = CachingProvider(inner, tmp_path, mode="record")
    summaries = run(run_configs([BAD, CLEAN], ["rules", "llm", "rules+llm"], provider))
    assert set(summaries) == {"rules", "llm", "rules+llm"}
    assert summaries["rules"].tp == 1 and summaries["llm"].tp == 1
    # both stages flagged line 2: that is one issue, so one comment, not a duplicate
    assert summaries["rules+llm"].tp == 1 and summaries["rules+llm"].duplicates == 0
    assert summaries["rules+llm"].comments == 1
    assert summaries["llm"].prompt_tokens > 0


def test_a_broken_model_is_reported_as_an_error_and_rules_still_score(tmp_path):
    provider = CachingProvider(FakeProvider([LLMError("down")], model="fake"), tmp_path, mode="record")
    summaries = run(run_configs([BAD], ["llm", "rules+llm"], provider))
    assert summaries["llm"].errors == 1 and summaries["llm"].tp == 0
    assert summaries["rules+llm"].errors == 1 and summaries["rules+llm"].tp == 1


def test_replay_gives_identical_numbers_without_calling_the_model(tmp_path):
    rec = CachingProvider(FakeProvider([llm_reply(2)], model="fake"), tmp_path, mode="record")
    first = run(run_configs([BAD, CLEAN], ["llm"], rec))["llm"]
    spy = FakeProvider(["unused"], model="fake")
    replay = CachingProvider(spy, tmp_path, mode="replay")
    second = run(run_configs([BAD, CLEAN], ["llm"], replay))["llm"]
    assert spy.calls == [] and (first.tp, first.fp, first.fn) == (second.tp, second.fp, second.fn)
    assert first.prompt_tokens == second.prompt_tokens


def test_rules_only_needs_no_provider():
    summaries = run(run_configs([BAD], ["rules"], None))
    assert summaries["rules"].tp == 1


# ---------------- detail report ----------------
from app.eval.report import format_details  # noqa: E402
from app.eval.runner import run_configs_detailed  # noqa: E402


def test_details_explain_every_imperfect_case_and_skip_perfect_ones(tmp_path):
    provider = CachingProvider(FakeProvider([llm_reply(1)], model="fake"), tmp_path, mode="record")  # wrong line
    summaries, results = run(run_configs_detailed([BAD, CLEAN], ["llm"], provider))
    assert summaries["llm"].fp == 1 and summaries["llm"].fn == 1
    text = format_details(results)
    assert "bad: missed line 2 (security)" in text
    assert "bad: unexpected line 1 (security) 'Shell injection' [llm-security]" in text
    assert "clean" not in text  # perfect cases are not listed


def test_details_mark_duplicates_and_noisy_clean_files():
    results = {"rules": run(evaluate([COMMENT], lambda: [RulesStage()]))}
    text = format_details(results)
    assert "comment: unexpected line 1" in text and "[rules]" in text


def test_nothing_to_report_when_every_case_is_perfect():
    results = {"rules": run(evaluate([BAD, CLEAN], lambda: [RulesStage()]))}
    assert format_details(results) == "All cases perfect."


# ---------------- the gate in the evaluation ----------------
def test_gated_and_ungated_configs_show_what_the_gate_changes(tmp_path):
    ai_says_nothing = CachingProvider(FakeProvider(['{"findings": []}'], model="fake"), tmp_path, mode="record")
    summaries = run(run_configs([COMMENT, BAD], ["rules+llm-ungated", "rules+llm"], ai_says_nothing))
    assert summaries["rules+llm-ungated"].false_alarm_cases == 1 and summaries["rules+llm-ungated"].held_back == 0
    assert summaries["rules+llm"].false_alarm_cases == 0 and summaries["rules+llm"].held_back == 2  # eval(...) and shell=True
    assert summaries["rules+llm"].tp == 0  # the price: the AI said nothing about the real bug, so it was held back too


# ---------------- confidence marks and the --model override ----------------
def test_evaluate_records_the_confidence_of_right_and_wrong_comments():
    (bad,) = run(evaluate([BAD], lambda: [RulesStage()]))
    (noisy,) = run(evaluate([COMMENT], lambda: [RulesStage()]))
    assert bad.marks == [(0.65, True)]      # shell=True on the labeled line
    assert noisy.marks == [(0.6, False)]    # eval( inside a comment on a clean file


def test_the_model_flag_selects_which_recordings_are_replayed(tmp_path):
    from app.eval.run import main_async, parse_args

    cases, cache, out = tmp_path / "cases", tmp_path / "cache", tmp_path / "out"
    cases.mkdir()
    (cases / "bad.py").write_text("import subprocess\nsubprocess.run(cmd, shell=True)  # EXPECT: security\n")
    rec = CachingProvider(FakeProvider([llm_reply(2)], model="m-recorded"), cache, mode="record")
    run(run_configs([BAD], ["llm"], rec))

    args = parse_args(["--config", "llm", "--mode", "replay", "--model", "m-recorded",
                       "--cases", str(cases), "--cache", str(cache), "--out", str(out)])
    run(main_async(args))

    (saved,) = list(out.glob("*.json"))
    data = json.loads(saved.read_text())
    assert data["model"] == "m-recorded" and data["summaries"]["llm"]["tp"] == 1
def test_evaluate_scores_the_same_comments_strictly_and_leniently(tmp_path):
    provider = CachingProvider(FakeProvider([llm_reply(1)], model="fake"), tmp_path, mode="record")  # one line above the label
    summaries, results = run(run_configs_detailed([BAD, CLEAN], ["llm"], provider))
    bad = {r.case_id: r for r in results["llm"]}["bad"]
    assert (bad.score.tp, bad.score.fp, bad.score.fn) == (0, 1, 1)
    assert (bad.lenient.tp, bad.lenient.fp, bad.lenient.fn) == (1, 0, 0)
    assert summaries["llm"].f1 == 0.0 and summaries["llm"].lenient_f1 == 1.0
