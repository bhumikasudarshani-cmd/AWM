"""The eval regression gate: replay the recorded model answers and fail if accuracy fell below the baseline."""
import asyncio
import json

import pytest

from app.eval.gate import Baseline, Floor, check_gate, load_baseline, parse_baseline
from app.eval.report import CaseResult, summarize
from app.eval.run import HERE, main_async, parse_args
from app.eval.score import CaseScore

BASELINE = Baseline(model="m", floors={"rules": Floor(precision=0.6, recall=0.9)})


def summary(tp, fp, fn, error=None):
    return summarize([CaseResult("a", False, CaseScore(tp, fp, fn, 0, tp + fp), error, 0, 0, 0)])


# ---------------- check_gate: pure ----------------

def test_passes_when_both_numbers_are_above_the_floor():
    assert check_gate({"rules": summary(9, 1, 0)}, BASELINE) == []


def test_exactly_at_the_floor_passes():
    # precision 6/10 = 0.6, recall 6/6 = 1.0
    assert check_gate({"rules": summary(6, 4, 0)}, BASELINE) == []


def test_precision_below_the_floor_fails_and_names_config_and_metric():
    (msg,) = check_gate({"rules": summary(5, 5, 0)}, BASELINE)
    assert "rules" in msg and "precision" in msg and "0.50" in msg and "0.60" in msg


def test_recall_below_the_floor_fails():
    (msg,) = check_gate({"rules": summary(8, 0, 2)}, BASELINE)
    assert "rules" in msg and "recall" in msg


def test_both_metrics_below_the_floor_report_two_failures():
    assert len(check_gate({"rules": summary(5, 5, 5)}, BASELINE)) == 2


def test_a_stage_error_fails_even_if_the_numbers_look_fine_and_says_to_re_record():
    msgs = check_gate({"rules": summary(9, 1, 0, error="no recorded response")}, BASELINE)
    assert any("error" in m and "re-record" in m for m in msgs)


def test_undefined_metric_fails_when_the_floor_is_above_zero():
    msgs = check_gate({"rules": summarize([CaseResult("a", True, CaseScore(0, 0, 0, 0, 0), None, 0, 0, 0)])}, BASELINE)
    assert len(msgs) == 2 and all("undefined" in m for m in msgs)


def test_a_config_in_the_baseline_that_was_not_run_fails():
    (msg,) = check_gate({}, BASELINE)
    assert "rules" in msg and "not run" in msg


def test_a_config_without_a_baseline_fails_so_nobody_adds_one_silently():
    (msg,) = check_gate({"rules": summary(9, 1, 0), "llm": summary(9, 1, 0)}, BASELINE)
    assert "llm" in msg and "no baseline" in msg


# ---------------- baseline file: parse and validate ----------------

def good(**over):
    data = {"model": "m", "configs": {"rules": {"precision": 0.5, "recall": 0.4}}}
    data.update(over)
    return json.dumps(data)


def test_parse_baseline_reads_model_and_floors():
    b = parse_baseline(good())
    assert b.model == "m" and b.floors == {"rules": Floor(0.5, 0.4)}


@pytest.mark.parametrize("text", [
    "not json", "[]", good(model=""), good(model=3), good(configs={}), good(configs=[]),
    good(configs={"rules": {"precision": 0.5}}),
    good(configs={"rules": {"precision": 1.5, "recall": 0.4}}),
    good(configs={"rules": {"precision": -0.1, "recall": 0.4}}),
    good(configs={"rules": {"precision": "high", "recall": 0.4}}),
    good(configs={"rules": {"precision": True, "recall": 0.4}}),  # True == 1 in Python; a floor of 1.0 by accident
    good(configs={"rules": {"precision": 0.5, "recall": 0.4, "f1": 0.4}}),
    good(extra=1),
])
def test_a_malformed_baseline_is_rejected(text):
    with pytest.raises(ValueError):
        parse_baseline(text)


def test_the_committed_baseline_covers_every_config_the_runner_knows():
    from app.eval.runner import CONFIG_NAMES

    assert set(load_baseline(HERE / "baseline.json").floors) == set(CONFIG_NAMES)


# ---------------- command line ----------------

@pytest.mark.parametrize("argv", [
    ["--gate", "--mode", "record"], ["--gate", "--mode", "live"],
    ["--gate", "--config", "rules"], ["--gate", "--cases", "app/eval/heldout"], ["--gate", "--model", "other"],
])
def test_gate_only_runs_on_all_configs_in_replay_on_the_dev_cases(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_gate_flag_alone_is_accepted():
    assert parse_args(["--gate"]).gate is True and parse_args([]).gate is False


def run_gate(tmp_path, baseline_path=None):
    argv = ["--gate", "--out", str(tmp_path)] + (["--baseline", str(baseline_path)] if baseline_path else [])
    asyncio.run(main_async(parse_args(argv)))


def test_gate_passes_on_the_committed_recordings_and_baseline(tmp_path, capsys):
    run_gate(tmp_path)
    assert "Gate: ok" in capsys.readouterr().out


def test_gate_exits_with_code_1_when_the_baseline_is_stricter_than_reality(tmp_path, capsys):
    strict = json.loads((HERE / "baseline.json").read_text(encoding="utf-8"))
    strict["configs"]["rules"] = {"precision": 1.0, "recall": 1.0}
    path = tmp_path / "strict.json"
    path.write_text(json.dumps(strict), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        run_gate(tmp_path, path)
    assert e.value.code == 1 and "Gate: FAILED" in capsys.readouterr().out

