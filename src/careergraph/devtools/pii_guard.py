"""Fail if personal files or secrets are tracked by git. Used by pre-commit and CI."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATHS = [
    re.compile(r"^profiles/me/"),
    re.compile(r"^\.env$"),
    re.compile(r"^outputs/"),
    re.compile(r"^data/[^/]+\.(db|sqlite)(-.*)?$"),
    re.compile(r"^data/cache/"),
]
ALLOWED_PDF_PREFIXES = ("data/demo/", "profiles/example/")
SECRET_PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    "Tavily key": re.compile(r"\btvly-[A-Za-z0-9]{16,}"),
    "LangSmith key": re.compile(r"\blsv2_[a-z]{2}_[A-Za-z0-9]{20,}"),
    "Private key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def tracked_files(root: Path) -> list[str]:
    """Return git-tracked (and staged) paths relative to root."""
    out = subprocess.run(
        ["git", "ls-files", "--cached"], cwd=root, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def find_problems(root: Path, files: list[str]) -> list[str]:
    """Return human-readable problems for forbidden paths and secret-looking content."""
    problems: list[str] = []
    for f in files:
        if any(p.search(f) for p in FORBIDDEN_PATHS):
            problems.append(f"personal/runtime file is tracked: {f}")
        if f.endswith(".pdf") and not f.startswith(ALLOWED_PDF_PREFIXES):
            problems.append(f"PDF outside demo/example dirs is tracked: {f}")
        path = root / f
        if f.startswith("tests/") or not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                problems.append(f"{name} pattern found in {f}")
    return problems


def main() -> int:
    """Entry point: print problems and return a non-zero exit code if any."""
    root = Path.cwd()
    problems = find_problems(root, tracked_files(root))
    for p in problems:
        print(f"PII/secret guard: {p}", file=sys.stderr)
    if not problems:
        print("PII/secret guard: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
