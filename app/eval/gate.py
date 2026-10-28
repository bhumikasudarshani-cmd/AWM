"""Regression gate for accuracy. CI replays the recorded model answers (free, offline, deterministic) and fails if
precision or recall of any config fell below the committed floor in baseline.json.

Because the answers are recorded, the numbers do not move unless the code, the prompt or the cases changed. A change
that lowers a number has to say so: lower the floor in the same pull request, where a reviewer sees it. A change to the
prompt invalidates the recordings (the key contains the prompt), so it must re-record with a live model in the same PR."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.eval.report import Summary

GATE_MAX_INPUT_TOKENS = 5000  # fixed, so a developer's .env cannot change the prompts and break the recording keys
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Floor:
    precision: float
    recall: float


@dataclass(frozen=True, slots=True)
class Baseline:
    model: str  # the model the answers were recorded with; replay needs exactly this name
    floors: dict[str, Floor]


def _unit(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{where} must be a number between 0 and 1, got {value!r}")
    return float(value)


def parse_baseline(text: str) -> Baseline:
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != {"model", "configs"}:
        raise ValueError('baseline must be an object with exactly the keys "model" and "configs"')
    model, configs = data["model"], data["configs"]
    if not isinstance(model, str) or not model.strip():
        raise ValueError('"model" must be a non-empty string')
    if not isinstance(configs, dict) or not configs:
        raise ValueError('"configs" must be a non-empty object')
    floors: dict[str, Floor] = {}
    for name, entry in configs.items():
        if not isinstance(entry, dict) or set(entry) != {"precision", "recall"}:
            raise ValueError(f'config {name!r} must have exactly "precision" and "recall"')
        floors[name] = Floor(_unit(entry["precision"], f"{name}.precision"), _unit(entry["recall"], f"{name}.recall"))
    return Baseline(model=model, floors=floors)


def load_baseline(path: str | Path) -> Baseline:
    return parse_baseline(Path(path).read_text(encoding="utf-8"))


def check_gate(summaries: dict[str, Summary], baseline: Baseline) -> list[str]:
    """Return one message per problem; an empty list means the gate passes."""
    problems: list[str] = []
    for name, floor in baseline.floors.items():
        s = summaries.get(name)
        if s is None:
            problems.append(f"{name}: in the baseline but not run")
            continue
        if s.errors:
            problems.append(f"{name}: {s.errors} case(s) had an error (a missing recording means the prompt or model "
                            "changed: re-record with --mode record and commit the new recordings)")
        for metric, value, minimum in (("precision", s.precision, floor.precision), ("recall", s.recall, floor.recall)):
            if value is None:
                if minimum > 0:
                    problems.append(f"{name}: {metric} is undefined (nothing to measure), the baseline is {minimum:.2f}")
            elif value + _EPS < minimum:
                problems.append(f"{name}: {metric} {value:.2f} is below the baseline {minimum:.2f}")
    for name in summaries:
        if name not in baseline.floors:
            problems.append(f"{name}: no baseline (add it to baseline.json before adding a config)")
    return problems
