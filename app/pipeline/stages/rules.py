"""Rule-based stage: cheap, deterministic checks on *added* lines only.

No LLM and no cost. It exercises the whole pipeline (parse, stage, filter,
publish) and later serves as an evidence source for the verifier.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.pipeline.models import Category, Evidence, Finding, ReviewContext, Severity

PLACEHOLDER_HINTS = (
    "example", "your_", "your-", "changeme", "change-me", "xxxx", "placeholder", "dummy",
    "<", ">", "${", "{{",
)
PY = frozenset({"python"})
JS = frozenset({"javascript", "typescript"})


def _is_placeholder(m: re.Match[str]) -> bool:
    value = m.group("val").lower()
    return any(h in value for h in PLACEHOLDER_HINTS)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    title: str
    explanation: str
    category: Category
    severity: Severity
    confidence: float
    pattern: re.Pattern[str]
    languages: frozenset[str] | None = None
    suggested_fix: str | None = None
    skip_if: Callable[[re.Match[str]], bool] | None = None


RULES: tuple[Rule, ...] = (
    Rule(
        "hardcoded-credential", "Possible hardcoded credential",
        "A secret-looking value is assigned in source code. Secrets committed to git stay in history.",
        "security", "high", 0.7,
        re.compile(
            r"""\b(api[_-]?key|secret|passwd|password|auth[_-]?token|access[_-]?key|token)\b\s*[:=]\s*(["'])(?P<val>[^"']{8,})\2""",
            re.I,
        ),
        suggested_fix="Load it from an environment variable or a secret manager, and rotate it if it was real.",
        skip_if=_is_placeholder,
    ),
    Rule(
        "aws-access-key", "AWS access key ID in source",
        "This matches the format of an AWS access key ID.",
        "security", "critical", 0.9,
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        suggested_fix="Revoke the key in AWS, then use IAM roles or environment-based credentials.",
    ),
    Rule(
        "private-key", "Private key committed",
        "A PEM private key header was added to the repository.",
        "security", "critical", 0.95,
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        suggested_fix="Remove it from the repo history and rotate the key.",
    ),
    Rule(
        "dynamic-eval", "Dynamic code evaluation",
        "eval() runs arbitrary code, which becomes remote code execution if any input is untrusted.",
        "security", "medium", 0.6,
        re.compile(r"\beval\s*\("), PY | JS,
        suggested_fix="Parse the data explicitly (for example json.loads or ast.literal_eval).",
    ),
    Rule(
        "dynamic-exec", "Dynamic code execution via exec()",
        "exec() runs arbitrary code, which becomes remote code execution if any input is untrusted.",
        "security", "medium", 0.6,
        re.compile(r"(?<![\w.])exec\s*\("), PY,
    ),
    Rule(
        "shell-true", "subprocess with shell=True",
        "shell=True passes the command through a shell, which allows command injection.",
        "security", "medium", 0.65,
        re.compile(r"shell\s*=\s*True"), PY,
        suggested_fix="Pass an argument list and leave shell=False.",
    ),
    Rule(
        "tls-verify-off", "TLS certificate verification disabled",
        "verify=False makes the connection vulnerable to man-in-the-middle attacks.",
        "security", "medium", 0.7,
        re.compile(r"verify\s*=\s*False"), PY,
        suggested_fix="Keep verification on; configure a CA bundle if you use a private CA.",
    ),
    Rule(
        "debug-leftover-py", "Debugger call left in code",
        "A breakpoint or pdb call will pause execution in production.",
        "maintainability", "medium", 0.8,
        re.compile(r"\b(?:pdb\.set_trace|breakpoint)\s*\("), PY,
    ),
    Rule(
        "debug-leftover-js", "debugger statement left in code",
        "A debugger statement will pause execution when dev tools are open.",
        "maintainability", "medium", 0.8,
        re.compile(r"^\s*debugger\s*;?\s*$"), JS,
    ),
)


class RulesStage:
    name = "rules"

    async def run(self, ctx: ReviewContext) -> list[Finding]:
        findings: list[Finding] = []
        for fd in ctx.files:
            for line in fd.added_lines():
                for rule in RULES:
                    if rule.languages and fd.language not in rule.languages:
                        continue
                    m = rule.pattern.search(line.text)
                    if not m or (rule.skip_if and rule.skip_if(m)):
                        continue
                    assert line.new_no is not None  # added lines always have a head-file number
                    findings.append(
                        Finding(
                            file=fd.path,
                            line_start=line.new_no,
                            line_end=line.new_no,
                            category=rule.category,
                            severity=rule.severity,
                            confidence=rule.confidence,
                            title=rule.title,
                            explanation=rule.explanation,
                            suggested_fix=rule.suggested_fix,
                            evidence=[Evidence(tool="rules", rule=rule.id)],
                            source_stage=self.name,
                            anchor_text=line.text.strip()[:200],
                        )
                    )
        return findings
