"""Drift guard: code, .env.example and config/*.yaml must document exactly the same knobs.

Fails when:
- code reads an env var that .env.example does not document,
- .env.example documents a variable that Settings does not define (or vice versa),
- a documented variable or YAML key is never used by the code,
- a variable or YAML key has no explanatory comment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from careergraph.config import (
    REPO_ROOT,
    CriteriaConfig,
    PricingConfig,
    ProfileConfig,
    SearchConfig,
    Settings,
    SkillsConfig,
)

ENV_EXAMPLE = REPO_ROOT / ".env.example"
CODE_DIRS = [REPO_ROOT / "src" / "careergraph", REPO_ROOT / "ui"]
CONFIG_FILE = REPO_ROOT / "src" / "careergraph" / "config.py"
YAML_MODELS: dict[str, type[BaseModel]] = {
    "search.yaml": SearchConfig,
    "criteria.yaml": CriteriaConfig,
    "profile.yaml": ProfileConfig,
    "skills.yaml": SkillsConfig,
    "pricing.yaml": PricingConfig,
}
# Scaffolding allowlist: knobs documented before the feature that uses them is built.
# PLAN.md tracks it; it MUST be empty when P10 is done (test_not_yet_wired_is_empty_at_release).
NOT_YET_WIRED: set[str] = set()

ENV_READ = re.compile(r"""os\.(?:environ\.get|getenv|environ\[)\(?\s*["']([A-Z][A-Z0-9_]*)["']""")


def _documented_env() -> dict[str, int]:
    lines = ENV_EXAMPLE.read_text().splitlines()
    return {
        m.group(1): i
        for i, line in enumerate(lines)
        if (m := re.match(r"^([A-Z][A-Z0-9_]*)=", line))
    }


def _code_text(exclude: Path | None = None) -> str:
    """All Python code (minus `exclude`) plus the LaTeX templates, which read profile fields."""
    parts = []
    for d in CODE_DIRS:
        for p in d.rglob("*.py"):
            if p != exclude:
                parts.append(p.read_text())
    parts += [p.read_text() for p in (REPO_ROOT / "templates").rglob("*.j2")]
    return "\n".join(parts)


def _used(name: str, code: str) -> bool:
    """Attribute access (`.name`) or a quoted key (`"name"`, e.g. criterion weights by name)."""
    return bool(re.search(rf"\.{name}\b|[\"']{name}[\"']", code))


def _model_fields(model: type[BaseModel]) -> set[str]:
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(name)
        ann = field.annotation
        for sub in (ann, *getattr(ann, "__args__", ())):
            if isinstance(sub, type) and issubclass(sub, BaseModel):
                names |= _model_fields(sub)
            for inner in getattr(sub, "__args__", ()):
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    names |= _model_fields(inner)
    return names


def test_env_example_matches_settings() -> None:
    documented = set(_documented_env())
    fields = {f.upper() for f in Settings.model_fields}
    assert documented - fields == set(), "documented in .env.example but not in Settings"
    assert fields - documented == set(), "Settings fields missing from .env.example"


def test_every_env_var_has_a_comment() -> None:
    lines = ENV_EXAMPLE.read_text().splitlines()
    missing = [n for n, i in _documented_env().items() if not lines[i - 1].startswith("#")]
    assert missing == []


def test_code_reads_only_documented_env_vars() -> None:
    read = set(ENV_READ.findall(_code_text()))
    assert read - set(_documented_env()) == set()


def test_every_setting_is_used_by_code() -> None:
    code = _code_text()  # config.py properties (db_url, search_config_path...) are real uses
    unused = [f for f in Settings.model_fields if f not in NOT_YET_WIRED and not _used(f, code)]
    assert unused == [], f"documented but unused settings: {unused}"


@pytest.mark.parametrize("filename", list(YAML_MODELS))
def test_every_yaml_key_is_used_by_code(filename: str) -> None:
    code = _code_text(exclude=CONFIG_FILE)
    fields = _model_fields(YAML_MODELS[filename])
    unused = sorted(f for f in fields if f not in NOT_YET_WIRED and not _used(f, code))
    assert unused == [], f"{filename}: documented but unused keys: {unused}"


@pytest.mark.parametrize("filename", list(YAML_MODELS))
def test_every_yaml_key_has_a_comment(filename: str) -> None:
    fields = _model_fields(YAML_MODELS[filename])
    for path in (REPO_ROOT / "config" / filename, REPO_ROOT / "data" / "demo" / filename):
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        bad = []
        for i, line in enumerate(lines):
            m = re.match(r"^\s*(?:-\s*)?([a-z_]+):", line)
            if not m or m.group(1) not in fields or line.lstrip().startswith("#"):
                continue
            prev = next((x for x in reversed(lines[:i]) if x.strip()), "")
            if "#" not in line and not prev.lstrip().startswith("#"):
                bad.append(f"{path.name}:{i + 1}: {line.strip()}")
        assert bad == [], f"keys without a comment: {bad}"


def test_settings_reads_dotenv_from_repo_root() -> None:
    env_file = Settings.model_config.get("env_file")
    assert env_file is not None and Path(str(env_file)).parent == REPO_ROOT


def test_not_yet_wired_entries_are_really_unused() -> None:
    """Shrink NOT_YET_WIRED as features land: an entry that is now used must be removed."""
    code = _code_text()
    stale = sorted(n for n in NOT_YET_WIRED if _used(n, code))
    assert stale == [], f"remove from NOT_YET_WIRED (now used): {stale}"
