"""Shared fixtures. Tests never read the developer's .env or shell settings."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from careergraph.config import Settings
from careergraph.skills import SkillNormalizer


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    yield


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Demo settings writing all state under tmp_path and ignoring .env."""
    base: dict[str, object] = {
        "app_mode": "demo",
        "data_dir": tmp_path / "data",
        "output_dir": tmp_path / "outputs",
        "cache_dir": tmp_path / "cache",
        "latex_engine": "none",
        "log_format": "console",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated demo settings."""
    return make_settings(tmp_path)


@pytest.fixture(scope="session")
def skills() -> SkillNormalizer:
    """Normaliser built from the shipped config/skills.yaml."""
    from careergraph.config import REPO_ROOT, SkillsConfig, load_yaml_model
    from careergraph.skills import SkillNormalizer

    return SkillNormalizer(load_yaml_model(REPO_ROOT / "config" / "skills.yaml", SkillsConfig))
