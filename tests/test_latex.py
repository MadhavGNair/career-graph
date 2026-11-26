"""LaTeX escaping, rendering (golden files), template overrides, graceful compilation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from careergraph.config import DEMO_DIR, REPO_ROOT, ProfileConfig, load_yaml_model
from careergraph.domain.models import CVData
from careergraph.latex.compile import build_command, compile_tex, detect_engine
from careergraph.latex.escape import latex_escape, url_escape
from careergraph.latex.render import make_env, render_pair, template_dirs
from careergraph.latex.sample import sample_documents

GOLDEN = Path(__file__).parent / "golden"
TEMPLATES = REPO_ROOT / "templates"


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("R&D 100% $5 #1 a_b {x}", r"R\&D 100\% \$5 \#1 a\_b \{x\}"),
        ("~ ^ \\", r"\textasciitilde{} \textasciicircum{} \textbackslash{}"),
        ("\\textbf{x}", r"\textbackslash{}textbf\{x\}"),
        ("€ – … <>", r"\texteuro{} -- \ldots{} \textless{}\textgreater{}"),
        (None, ""),
    ],
)
def test_latex_escape(raw: object, escaped: str) -> None:
    assert latex_escape(raw) == escaped


def test_url_escape_only_touches_url_specials() -> None:
    assert url_escape("https://x.example/a_b?q=1#frag%20") == r"https://x.example/a_b?q=1\#frag\%20"
    assert url_escape("javascript:alert(1)") == ""


def _profile() -> ProfileConfig:
    return load_yaml_model(DEMO_DIR / "profile" / "profile.yaml", ProfileConfig)


def test_render_sample_matches_golden_files() -> None:
    cv, letter = sample_documents(_profile())
    cv_tex, letter_tex = render_pair(cv, letter, [TEMPLATES])
    if os.environ.get("UPDATE_GOLDEN") == "1":
        (GOLDEN / "cv_sample.tex").write_text(cv_tex)
        (GOLDEN / "letter_sample.tex").write_text(letter_tex)
    assert cv_tex == (GOLDEN / "cv_sample.tex").read_text()
    assert letter_tex == (GOLDEN / "letter_sample.tex").read_text()
    assert r"38\% \& shipped R\&D tooling in C\# and C++ (budget: \$1,000\_000)" in cv_tex
    assert r"\href{mailto:sam.demo@example.com}" in cv_tex


def test_injected_latex_in_claims_cannot_execute() -> None:
    cv, letter = sample_documents(_profile())
    cv.summary[0].text = r"\input{/etc/passwd} \immediate\write18{rm -rf /}"
    cv_tex, _ = render_pair(cv, letter, [TEMPLATES])
    assert r"\input{" not in cv_tex and r"\write18" not in cv_tex


def test_strict_undefined(tmp_path: Path) -> None:
    (tmp_path / "cv").mkdir()
    (tmp_path / "cv" / "default.tex.j2").write_text("((( cv.nope.deeper )))")
    with pytest.raises(UndefinedError):
        make_env([tmp_path]).get_template("cv/default.tex.j2").render(
            cv=CVData(name="x").model_dump()
        )


def test_profile_templates_override_shipped(tmp_path: Path) -> None:
    override = tmp_path / "docs" / "templates" / "cv"
    override.mkdir(parents=True)
    (override / "default.tex.j2").write_text("MY TEMPLATE ((( cv.name )))")
    cv, letter = sample_documents(_profile())
    cv_tex, letter_tex = render_pair(cv, letter, template_dirs(TEMPLATES, tmp_path / "docs"))
    assert cv_tex == "MY TEMPLATE Sam Demo" and "\\documentclass" in letter_tex


def test_compile_degrades_without_engine(tmp_path: Path) -> None:
    tex = tmp_path / "x.tex"
    tex.write_text("x")
    r = compile_tex(tex, "none", 10)
    assert not r.ok and r.pdf is None and "wrote .tex only" in r.message
    assert detect_engine("none") is None


def test_engine_commands_disable_shell_escape(tmp_path: Path) -> None:
    assert "--untrusted" in build_command("tectonic", tmp_path / "a.tex")
    assert "-no-shell-escape" in build_command("pdflatex", tmp_path / "a.tex")


@pytest.mark.skipif(
    detect_engine("auto") is None, reason="no LaTeX engine installed (tectonic/pdflatex)"
)
def test_sample_compiles_with_installed_engine(tmp_path: Path) -> None:
    cv, letter = sample_documents(_profile())
    cv_tex, _ = render_pair(cv, letter, [TEMPLATES])
    (tmp_path / "cv.tex").write_text(cv_tex)
    r = compile_tex(tmp_path / "cv.tex", "auto", 180)
    assert r.ok, r.message
    assert shutil.which(r.engine)
