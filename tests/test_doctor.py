"""`make doctor` checks."""

from __future__ import annotations

from pathlib import Path

from careergraph.doctor import run_checks
from tests.conftest import make_settings


def test_doctor_demo_has_no_failures(tmp_path: Path) -> None:
    checks = run_checks(make_settings(tmp_path))
    assert not [c for c in checks if c.status == "FAIL"], checks
    names = {c.name for c in checks}
    assert {"mode", "config", "models", "latex", "database", "profile", "spend", "ui"} <= names


def test_doctor_live_without_key_fails_with_action(tmp_path: Path) -> None:
    checks = run_checks(make_settings(tmp_path, app_mode="live"))
    model = [c for c in checks if c.name.startswith("model:")]
    assert model and all(c.status == "FAIL" and "ANTHROPIC_API_KEY" in c.action for c in model)
    profile = next(c for c in checks if c.name == "profile")
    assert profile.status == "FAIL"  # placeholder name in config/profile.yaml


def test_doctor_production_requires_password(tmp_path: Path) -> None:
    checks = run_checks(make_settings(tmp_path, app_env="production"))
    ui = next(c for c in checks if c.name == "ui")
    assert ui.status == "FAIL"
