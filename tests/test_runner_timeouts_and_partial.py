import asyncio

from app.diff.builder import build_file_diff
from app.diff.coverage import Coverage, SkippedFile
from app.github.publisher import build_review_payload
from app.pipeline.models import ReviewConfig, ReviewContext
from app.pipeline.runner import run_pipeline


def ctx():
    fd = build_file_diff({"filename": "a.py", "status": "modified", "changes": 1, "additions": 1, "patch": "@@ -1 +1,2 @@\n a\n+b"})
    return ReviewContext("o/r", 1, "abcdef1234", "t", "", "me", [fd], Coverage(reviewed=["a.py"]), ReviewConfig())


class Slow:
    def __init__(self, name, delay, timeout=None):
        self.name, self.delay = name, delay
        if timeout is not None:
            self.timeout = timeout

    async def run(self, c):
        await asyncio.sleep(self.delay)
        return []


def test_a_stage_can_declare_its_own_longer_timeout():
    res = asyncio.run(run_pipeline(ctx(), [Slow("short", 0.2), Slow("patient", 0.2, timeout=2.0)], stage_timeout=0.05))
    errors = {r.stage: r.error for r in res.stage_results}
    assert errors["short"] is not None and errors["patient"] is None


def test_summary_lists_files_that_were_only_partly_reviewed():
    c = ctx()
    c.coverage.partial.append(SkippedFile("big.py", "AI security review skipped: too large for one model call"))
    body = build_review_payload(c, [], [], checks=("rules", "llm-security"))["body"]
    assert "Only partly reviewed: 1 file(s)" in body and "`big.py`: AI security review skipped" in body
    assert "AI security review" in body.split("Checks run:")[1].splitlines()[0]
