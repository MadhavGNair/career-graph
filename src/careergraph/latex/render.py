"""Render CV and letter .tex files with Jinja2 using LaTeX-safe delimiters:

    ((( value )))       print (always escaped)
    ((* if x *)) ... ((* endif *))   statements
    ((# comment #))

Template lookup order: <profile documents dir>/templates/ first (your own), then templates/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from careergraph.domain.models import CVData, LetterData
from careergraph.latex.compile import CompileResult, compile_tex
from careergraph.latex.escape import LatexSafe, latex_escape, url_escape


def _finalize(value: Any) -> str:
    if isinstance(value, LatexSafe):
        return value
    return latex_escape(value)


def make_env(template_dirs: list[Path]) -> Environment:
    """Jinja2 environment with LaTeX-safe delimiters and strict undefined variables."""
    env = Environment(  # noqa: S701 - autoescape is HTML-specific; LaTeX escaping is done by finalize
        loader=FileSystemLoader([str(d) for d in template_dirs if d.exists()]),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
        line_statement_prefix=None,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        finalize=_finalize,
        keep_trailing_newline=True,
    )
    env.filters["url"] = url_escape
    return env


def template_dirs(templates_dir: Path, profile_docs_dir: Path) -> list[Path]:
    """User overrides first, then the shipped templates."""
    return [profile_docs_dir / "templates", templates_dir]


def render_pair(
    cv: CVData, letter: LetterData, dirs: list[Path], name: str = "default"
) -> tuple[str, str]:
    """Render (cv_tex, letter_tex) strings."""
    env = make_env(dirs)
    cv_tex = env.get_template(f"cv/{name}.tex.j2").render(cv=cv.model_dump())
    letter_tex = env.get_template(f"letter/{name}.tex.j2").render(letter=letter.model_dump())
    return cv_tex, letter_tex


def write_and_compile(
    cv: CVData, letter: LetterData, dirs: list[Path], out_dir: Path, engine: str, timeout: int
) -> tuple[Path, Path, list[CompileResult]]:
    """Write cv.tex and letter.tex into out_dir and try to compile both."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_tex, letter_tex = render_pair(cv, letter, dirs)
    cv_path, letter_path = out_dir / "cv.tex", out_dir / "letter.tex"
    cv_path.write_text(cv_tex, encoding="utf-8")
    letter_path.write_text(letter_tex, encoding="utf-8")
    return cv_path, letter_path, [compile_tex(p, engine, timeout) for p in (cv_path, letter_path)]
