from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(slots=True)
class Summary:
    cases: int
    clean_cases: int
    false_alarm_cases: int  # clean files that still got a comment
    errors: int
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


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def summarize(results: list[CaseResult]) -> Summary:
    tp = sum(r.score.tp for r in results)
    fp = sum(r.score.fp for r in results)
    fn = sum(r.score.fn for r in results)
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision is not None and recall is not None else None)
    comments = sum(r.score.comments for r in results)
    return Summary(
        cases=len(results),
        clean_cases=sum(1 for r in results if r.is_clean),
        false_alarm_cases=sum(1 for r in results if r.is_clean and r.score.comments > 0),
        errors=sum(1 for r in results if r.error),
        tp=tp, fp=fp, fn=fn, duplicates=sum(r.score.duplicates for r in results), comments=comments,
        precision=precision, recall=recall, f1=f1,
        comments_per_case=comments / len(results) if results else 0.0,
        duration_ms=sum(r.duration_ms for r in results),
        prompt_tokens=sum(r.prompt_tokens for r in results),
        completion_tokens=sum(r.completion_tokens for r in results),
    )


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def to_markdown(summaries: dict[str, Summary]) -> str:
    head = ("| Config | Precision | Recall | F1 | Comments/case | Duplicates | False alarms (clean files) "
            "| Errors | Time (s) | Tokens in/out |")
    lines = [head, "|" + "---|" * 10]
    for name, s in summaries.items():
        lines.append(
            f"| {name} | {_fmt(s.precision)} | {_fmt(s.recall)} | {_fmt(s.f1)} | {s.comments_per_case:.2f} "
            f"| {s.duplicates} | {s.false_alarm_cases}/{s.clean_cases} | {s.errors} "
            f"| {s.duration_ms / 1000:.1f} | {s.prompt_tokens}/{s.completion_tokens} |"
        )
    return "\n".join(lines)
