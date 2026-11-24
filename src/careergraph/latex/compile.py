"""Optional PDF compilation through tectonic or pdflatex. Degrades to .tex-only output."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Engine = Literal["tectonic", "pdflatex"]


@dataclass(frozen=True)
class CompileResult:
    """Outcome of one compile attempt."""

    pdf: Path | None
    engine: str
    ok: bool
    message: str


def detect_engine(preference: str) -> Engine | None:
    """Pick an engine from LATEX_ENGINE (auto prefers tectonic). None when unavailable."""
    if preference == "none":
        return None
    candidates: list[Engine] = (
        ["tectonic", "pdflatex"] if preference == "auto" else [preference]  # type: ignore[list-item]
    )
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def build_command(engine: Engine, tex: Path) -> list[str]:
    """Return a non-interactive, no-shell-escape command line for the engine."""
    if engine == "tectonic":
        # Tectonic V1 CLI (verified from the Tectonic book): -o OUTDIR, --untrusted.
        return ["tectonic", "--untrusted", "-o", str(tex.parent), str(tex)]
    return [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        f"-output-directory={tex.parent}",
        str(tex),
    ]


def compile_tex(tex: Path, preference: str, timeout: int) -> CompileResult:
    """Compile tex to PDF if an engine exists. Never raises for missing engines or errors."""
    engine = detect_engine(preference)
    if engine is None:
        return CompileResult(None, "none", False, "no LaTeX engine found; wrote .tex only")
    try:
        proc = subprocess.run(
            build_command(engine, tex),
            cwd=tex.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(None, engine, False, f"{engine} timed out after {timeout}s")
    pdf = tex.with_suffix(".pdf")
    if proc.returncode == 0 and pdf.exists():
        return CompileResult(pdf, engine, True, "compiled")
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
    return CompileResult(None, engine, False, f"{engine} failed: " + " | ".join(tail))
