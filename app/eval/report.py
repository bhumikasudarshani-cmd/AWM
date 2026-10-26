from __future__ import annotations

from dataclasses import dataclass, field

from app.eval.score import CaseScore


@dataclass(slots=True)
class CaseResult:
    case_id: str
    is_clean: bool
    score: CaseScore
    error: str | None
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    details: list[str] = field(default_factory=list)
    held_back: int = 0
    marks: list[tuple[float, bool]] = field(default_factory=list)  # (confidence, was it correct)


@dataclass(slots=True)
class Summary:
    cases: int
    clean_cases: int
    false_alarm_cases: int  # clean files that still got a comment
    errors: int
    held_back: int
    tp: int
    fp: int
    fn: int
    duplicates: int
    comments: int
    precision: float | None
    recall: float | None
    f1: float | None
    comments_per_case: float
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    mean_conf_correct: float | None = None
    mean_conf_wrong: float | None = None


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def summarize(results: list[CaseResult]) -> Summary:
    tp = sum(r.score.tp for r in results)
    fp = sum(r.score.fp for r in results)
    fn = sum(r.score.fn for r in results)
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision is not None and recall is not None else None)
    comments = sum(r.score.comments for r in results)
    right = [c for r in results for c, ok in r.marks if ok]
    wrong = [c for r in results for c, ok in r.marks if not ok]
    return Summary(
        cases=len(results),
        clean_cases=sum(1 for r in results if r.is_clean),
        false_alarm_cases=sum(1 for r in results if r.is_clean and r.score.comments > 0),
        errors=sum(1 for r in results if r.error),
        held_back=sum(r.held_back for r in results),
        tp=tp, fp=fp, fn=fn, duplicates=sum(r.score.duplicates for r in results), comments=comments,
        precision=precision, recall=recall, f1=f1,
        comments_per_case=comments / len(results) if results else 0.0,
        duration_ms=sum(r.duration_ms for r in results),
        prompt_tokens=sum(r.prompt_tokens for r in results),
        completion_tokens=sum(r.completion_tokens for r in results),
        mean_conf_correct=sum(right) / len(right) if right else None,
        mean_conf_wrong=sum(wrong) / len(wrong) if wrong else None,
    )


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def to_markdown(summaries: dict[str, Summary]) -> str:
    head = ("| Config | Precision | Recall | F1 | Comments/case | Duplicates | False alarms (clean files) "
            "| Held back | Errors | Time (s) | Tokens in/out |")
    lines = [head, "|" + "---|" * 11]
    for name, s in summaries.items():
        lines.append(
            f"| {name} | {_fmt(s.precision)} | {_fmt(s.recall)} | {_fmt(s.f1)} | {s.comments_per_case:.2f} "
            f"| {s.duplicates} | {s.false_alarm_cases}/{s.clean_cases} | {s.held_back} | {s.errors} "
            f"| {s.duration_ms / 1000:.1f} | {s.prompt_tokens}/{s.completion_tokens} |"
        )
    return "\n".join(lines)


def format_details(results_by_config: dict[str, list[CaseResult]]) -> str:
    """List every case that was not perfect, per configuration, and say what went wrong."""
    blocks: list[str] = []
    for name, results in results_by_config.items():
        lines = [f"  {r.case_id}: {d}" for r in results for d in r.details]
        if lines:
            blocks.append(f"[{name}]\n" + "\n".join(lines))
    return "\n\n".join(blocks) if blocks else "All cases perfect."


def confidence_sweep(
    results: list[CaseResult], thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
) -> list[tuple[float, float | None, float | None, int]]:
    """What would precision, recall and the number of comments be if min_confidence were raised?
    Returns (threshold, precision, recall, comments). Computed on the same data it describes, so it shows
    whether confidence separates right from wrong comments at all, not how a tuned threshold would generalise."""
    marks = [m for r in results for m in r.marks]
    expected = sum(r.score.tp + r.score.fn for r in results)
    rows = []
    for t in thresholds:
        kept = [ok for c, ok in marks if c >= t]
        tp = sum(kept)
        rows.append((t, _ratio(tp, len(kept)), _ratio(tp, expected), len(kept)))
    return rows


def format_sweep(results_by_config: dict[str, list[CaseResult]]) -> str:
    lines = ["Confidence sweep (precision / recall / comments if min_confidence were raised):"]
    for name, results in results_by_config.items():
        if not any(r.marks for r in results):
            continue
        cells = [
            f">={t:g} P{_fmt(p)} R{_fmt(r)} n{n}" for t, p, r, n in confidence_sweep(results)
        ]
        lines.append(f"  {name}: " + " | ".join(cells))
    return "\n".join(lines)
