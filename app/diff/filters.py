"""Decide which changed files are worth reviewing, and detect their language."""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Iterable

LOCKFILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock",
    "cargo.lock", "go.sum", "composer.lock", "gemfile.lock", "uv.lock",
})
BINARY_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".pdf", ".zip", ".tar", ".gz",
    ".tgz", ".7z", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".mov", ".so",
    ".dll", ".exe", ".class", ".jar", ".pyc", ".bin", ".onnx", ".pt",
})
IGNORED_DIRS = frozenset({
    "node_modules", "vendor", "dist", "build", "__pycache__", "site-packages", ".venv", "venv",
})
GENERATED_SUFFIXES = (
    ".min.js", ".min.css", ".map", "_pb2.py", "_pb2_grpc.py", ".pb.go", ".generated.ts",
)
LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".go": "go",
    ".java": "java", ".rb": "ruby", ".rs": "rust", ".php": "php", ".cs": "csharp",
    ".sh": "shell", ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".md": "markdown",
    ".sql": "sql", ".html": "html", ".css": "css",
}


def normalize(path: str) -> str:
    return path.replace("\\", "/")


def detect_language(path: str) -> str | None:
    return LANGUAGES.get(posixpath.splitext(normalize(path))[1].lower())


def classify_path(path: str, extra_patterns: Iterable[str] = ()) -> str | None:
    """Return a human-readable reason to skip this path, or None to review it."""
    p = normalize(path)
    name = posixpath.basename(p).lower()
    if posixpath.splitext(name)[1] in BINARY_EXTS:
        return "binary file"
    if name in LOCKFILES:
        return "lockfile"
    if name.endswith(GENERATED_SUFFIXES):
        return "generated file"
    if IGNORED_DIRS.intersection(p.split("/")[:-1]):
        return "vendored or build directory"
    parts = p.split("/")
    # match a pattern against the full path and every trailing sub-path, so "migrations/*"
    # also catches "db/migrations/001.sql"
    candidates = ["/".join(parts[i:]) for i in range(len(parts))]
    for pattern in extra_patterns:
        if any(fnmatch.fnmatch(c, pattern) for c in candidates):
            return "ignored by config"
    return None
