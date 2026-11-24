"""Config loading and validation messages."""

from __future__ import annotations

from pathlib import Path

import pytest

from careergraph.config import (
    REPO_ROOT,
    ConfigErrors,
    CriteriaConfig,
    PricingConfig,
    ProfileConfig,
    SearchConfig,
    Settings,
    SkillsConfig,
    load_app_config,
    load_settings,
    load_yaml_model,
)

EXAMPLES = [
    ("search.yaml", SearchConfig),
    ("criteria.yaml", CriteriaConfig),
    ("profile.yaml", ProfileConfig),
    ("skills.yaml", SkillsConfig),
    ("pricing.yaml", PricingConfig),
]


@pytest.mark.parametrize(("name", "model"), EXAMPLES)
def test_shipped_example_configs_are_valid(name: str, model: type) -> None:
    load_yaml_model(REPO_ROOT / "config" / name, model)


def test_demo_configs_are_valid(settings: Settings) -> None:
    cfg = load_app_config(settings)
    assert cfg.profile.identity.name == "Sam Demo"
    assert all(not s.is_placeholder for s in cfg.search.sources)


def test_live_example_sources_are_placeholders() -> None:
    cfg = load_yaml_model(REPO_ROOT / "config" / "search.yaml", SearchConfig)
    assert cfg.sources and all(s.is_placeholder and not s.enabled for s in cfg.sources)


def test_unknown_key_names_file_key_and_fix(tmp_path: Path) -> None:
    bad = tmp_path / "criteria.yaml"
    bad.write_text("weights:\n  must_hve: 0.3\n")
    with pytest.raises(ConfigErrors) as exc:
        load_yaml_model(bad, CriteriaConfig)
    err = exc.value.errors[0]
    assert err.key == "weights.must_hve"
    assert "unknown key" in err.fix
    assert "criteria.yaml" in exc.value.render()


def test_bad_literal_value_is_explained(tmp_path: Path) -> None:
    bad = tmp_path / "search.yaml"
    bad.write_text("locations:\n  remote: sometimes\n")
    with pytest.raises(ConfigErrors) as exc:
        load_yaml_model(bad, SearchConfig)
    assert exc.value.errors[0].key == "locations.remote"
    assert "allowed values" in exc.value.errors[0].fix


def test_invalid_yaml_reports_line(tmp_path: Path) -> None:
    bad = tmp_path / "skills.yaml"
    bad.write_text("aliases:\n  python: [py\n")
    with pytest.raises(ConfigErrors) as exc:
        load_yaml_model(bad, SkillsConfig)
    assert "invalid YAML" in exc.value.errors[0].problem


def test_missing_file_suggests_init(tmp_path: Path) -> None:
    with pytest.raises(ConfigErrors) as exc:
        load_yaml_model(tmp_path / "nope.yaml", SkillsConfig)
    assert "make init" in exc.value.errors[0].fix


def test_bad_env_value_names_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MODE", "production")
    with pytest.raises(ConfigErrors) as exc:
        load_settings(_env_file=None)
    assert exc.value.errors[0].key == "APP_MODE"
    assert ".env.example" in exc.value.errors[0].fix


def test_model_string_must_have_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHEAP_MODEL", "claude-haiku-5-5")
    with pytest.raises(ConfigErrors) as exc:
        load_settings(_env_file=None)
    assert exc.value.errors[0].key == "CHEAP_MODEL"


def test_blank_optional_values_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_USD_PER_RUN", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    s = load_settings(_env_file=None)
    assert s.max_usd_per_run is None and s.anthropic_api_key is None


def test_demo_and_live_use_separate_databases(tmp_path: Path) -> None:
    demo = Settings(_env_file=None, data_dir=tmp_path)  # type: ignore[call-arg]
    live = Settings(_env_file=None, data_dir=tmp_path, app_mode="live")  # type: ignore[call-arg]
    assert demo.db_url != live.db_url and "demo" in demo.db_url


def test_weights_normalise() -> None:
    w = CriteriaConfig().weights.normalised()
    assert abs(sum(w.values()) - 1.0) < 1e-9
