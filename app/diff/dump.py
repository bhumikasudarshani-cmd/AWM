"""Dev helper: save the raw 'list files' response so it can become a test fixture."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

KEEP = ("filename", "status", "previous_filename", "additions", "deletions", "changes", "patch")


def dump_files(repo: str, number: int, sha: str, raw_files: list[dict[str, Any]], directory: str = "fixtures_dump") -> Path:
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{repo}_pr{number}_{sha[:7]}") + ".json"
    path = out_dir / name
    slim = [{k: f[k] for k in KEEP if k in f} for f in raw_files]
    path.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return path
