"""Test helpers: demo services wired to temp dirs."""

from __future__ import annotations

from pathlib import Path

from careergraph.config import load_app_config
from careergraph.service.wiring import Services, build_services
from tests.conftest import make_settings


def demo_services(tmp_path: Path, **overrides: object) -> Services:
    """Fresh demo services with isolated DB/cache/output under tmp_path."""
    return build_services(load_app_config(make_settings(tmp_path, **overrides)))
