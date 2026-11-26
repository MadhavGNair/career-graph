"""Streamlit AppTest smoke tests: every page renders headlessly, and the shortlist/review forms
drive the service end to end."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from careergraph.config import REPO_ROOT

UI = REPO_ROOT / "ui"
PAGES = ["app.py", "pages/1_Run.py", "pages/2_Shortlist.py", "pages/3_Documents.py",
         "pages/4_Tracker.py", "pages/5_Insights.py"]  # fmt: skip


@pytest.fixture
def ui_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("LATEX_ENGINE", "none")
    monkeypatch.setenv("LOG_FORMAT", "console")
    yield tmp_path


def _run(page: str) -> AppTest:
    at = AppTest.from_file(str(UI / page), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(ui_env: Path, page: str) -> None:
    at = _run(page)
    assert at.title and "Demo mode" in " ".join(c.value for c in at.caption)


def test_password_gate(ui_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_PASSWORD", "s3cret")
    at = _run("app.py")
    assert len(at.text_input) == 1 and not at.title
    at.text_input[0].input("wrong").run()
    assert not at.title
    at.text_input[0].input("s3cret").run()
    assert at.title[0].value == "CareerGraph"


def test_production_requires_password(ui_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    at = _run("app.py")
    assert "UI_PASSWORD" in at.error[0].value


def test_run_shortlist_review_flow_through_ui(ui_env: Path) -> None:
    run = _run("pages/1_Run.py")
    run.button[0].click().run()
    assert not run.exception and any("Paused for your shortlist" in s.value for s in run.success)

    shortlist = _run("pages/2_Shortlist.py")
    assert shortlist.expander and shortlist.dataframe
    shortlist.radio(key=f"d-{_first_job(shortlist)}").set_value("approve")
    shortlist.button[0].click().run()
    assert not shortlist.exception, [e.value for e in shortlist.exception]
    assert any("document review" in s.value for s in shortlist.success)

    docs = _run("pages/3_Documents.py")
    assert docs.text_area  # one editable text area per claim
    docs.button[0].click().run()
    assert not docs.exception
    assert any("Completed" in s.value for s in docs.success)

    tracker = _run("pages/4_Tracker.py")
    assert tracker.dataframe[0].value.shape[0] == 1
    insights = _run("pages/5_Insights.py")
    assert not insights.info  # trend and usage present


def _first_job(at: AppTest) -> str:
    key = next(r.key for r in at.radio if r.key and r.key.startswith("d-"))
    return key[2:]
