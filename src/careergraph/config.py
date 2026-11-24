"""Settings (.env) and YAML config loading with friendly, actionable validation errors.

Everything a user can change lives in `.env` (secrets, mode, models, budgets, switches) or
`config/*.yaml` (search, criteria, profile, skills, pricing). This module is the only place that
reads either. Every field here is documented in `.env.example` or the YAML files, and
`tests/test_drift_guard.py` fails if the two drift apart.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO_ROOT / "data" / "demo"


class ConfigError(Exception):
    """A config problem that names the file, the key and a fix (never a raw traceback)."""

    def __init__(self, file: str, key: str, problem: str, fix: str) -> None:
        self.file, self.key, self.problem, self.fix = file, key, problem, fix
        super().__init__(f"{file}: {key}: {problem}. Fix: {fix}")

    def render(self) -> str:
        """Return a human-readable multi-line message."""
        return (
            f"Config error in {self.file}\n  key:     {self.key}\n"
            f"  problem: {self.problem}\n  fix:     {self.fix}"
        )


class ConfigErrors(Exception):
    """Several ConfigErrors from one file, reported together."""

    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))

    def render(self) -> str:
        """Return all errors, one block each."""
        return "\n\n".join(e.render() for e in self.errors)


# --------------------------------------------------------------------------------------------
# .env settings
# --------------------------------------------------------------------------------------------


class Settings(BaseSettings):
    """Process settings from environment variables and `.env`. See `.env.example`."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_mode: Literal["demo", "live"] = "demo"
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    data_dir: Path = Path("data")
    output_dir: Path = Path("outputs")
    cache_dir: Path = Path("data/cache")
    config_dir: Path = Path("config")
    templates_dir: Path = Path("templates")
    database_url: str = ""

    cheap_model: str = "anthropic:claude-haiku-5-5"
    strong_model: str = "anthropic:claude-sonnet-5-5"
    cheap_effort: Literal["", "low", "medium", "high"] = "low"
    strong_effort: Literal["", "low", "medium", "high"] = "medium"
    max_output_tokens_per_call: int = Field(default=8000, ge=256, le=64000)
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    anthropic_api_key: SecretStr | None = None

    max_jobs_per_run: int = Field(default=30, ge=1)
    max_tokens_per_run: int = Field(default=400_000, ge=1000)
    max_tokens_per_day: int = Field(default=1_500_000, ge=1000)
    max_usd_per_run: float | None = Field(default=None, gt=0)
    max_usd_per_day: float | None = Field(default=None, gt=0)
    max_revisions: int = Field(default=3, ge=0, le=10)

    enable_company_research: bool = False
    research_max_steps: int = Field(default=4, ge=1, le=12)
    research_max_tokens: int = Field(default=20_000, ge=1000)
    search_provider: Literal["site", "tavily", "brave"] = "site"
    tavily_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None
    enable_match_rationale: bool = True
    require_document_review: bool = True

    latex_engine: Literal["auto", "tectonic", "pdflatex", "none"] = "auto"
    latex_timeout_seconds: int = Field(default=120, ge=5)

    embedding_backend: Literal["auto", "hashing", "fastembed"] = "auto"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    github_token: SecretStr | None = None
    http_timeout_seconds: float = Field(default=20.0, gt=0)
    http_max_bytes: int = Field(default=3_000_000, ge=10_000)
    http_min_interval_seconds: float = Field(default=1.0, ge=0)
    http_contact: str = ""

    ui_host: str = "127.0.0.1"
    ui_port: int = Field(default=8501, ge=1, le=65535)
    ui_password: SecretStr | None = None

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "careergraph"

    demo_fabricate_job: str = "gh-nimbus-analytics-4001"

    @field_validator(
        "max_usd_per_run",
        "max_usd_per_day",
        "anthropic_api_key",
        "tavily_api_key",
        "brave_api_key",
        "github_token",
        "ui_password",
        "langsmith_api_key",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: Any) -> Any:
        return None if isinstance(v, str) and v.strip() == "" else v

    @field_validator("cheap_model", "strong_model")
    @classmethod
    def _provider_model(cls, v: str) -> str:
        if ":" not in v or not all(v.split(":", 1)):
            raise ValueError("must look like 'provider:model', e.g. anthropic:claude-haiku-5-5")
        return v

    # ---- derived paths ------------------------------------------------------------------
    def resolve(self, p: Path) -> Path:
        """Resolve a configured path relative to the repo root."""
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def is_demo(self) -> bool:
        """Whether the fake LLM and fixtures are in use."""
        return self.app_mode == "demo"

    @property
    def db_url(self) -> str:
        """App database URL. Demo and live use separate SQLite files so data never mixes."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolve(self.data_dir) / f'careergraph-{self.app_mode}.db'}"

    @property
    def is_postgres(self) -> bool:
        """True when DATABASE_URL points at Postgres."""
        return self.db_url.startswith(("postgresql", "postgres"))

    @property
    def search_config_path(self) -> Path:
        """Demo uses the fictional search config so the demo is reproducible."""
        if self.is_demo:
            return DEMO_DIR / "search.yaml"
        return self.resolve(self.config_dir) / "search.yaml"

    @property
    def profile_config_path(self) -> Path:
        """Demo uses the fictional Sam Demo profile."""
        if self.is_demo:
            return DEMO_DIR / "profile" / "profile.yaml"
        return self.resolve(self.config_dir) / "profile.yaml"

    @property
    def effective_embedding_backend(self) -> Literal["hashing", "fastembed"]:
        """`auto` means hashing in demo (no download) and fastembed in live."""
        if self.embedding_backend == "auto":
            return "hashing" if self.is_demo else "fastembed"
        return self.embedding_backend


ENV_EXAMPLE = REPO_ROOT / ".env.example"


def load_settings(**overrides: Any) -> Settings:
    """Load settings from env/.env and raise ConfigErrors with fixes on invalid values."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        raise ConfigErrors(
            [
                ConfigError(
                    ".env",
                    str(err["loc"][0]).upper() if err["loc"] else "?",
                    err["msg"],
                    "Edit the value in .env; allowed values and defaults are in the comment "
                    "above the same variable in .env.example.",
                )
                for err in exc.errors()
            ]
        ) from None


# --------------------------------------------------------------------------------------------
# YAML config models (extra keys are forbidden so typos surface immediately)
# --------------------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSpec(_Strict):
    type: Literal["greenhouse", "lever", "ashby", "rss"]
    slug: str = ""
    url: str = ""
    company: str = ""
    enabled: bool = True
    region: Literal["global", "eu"] = "global"

    @property
    def is_placeholder(self) -> bool:
        """True for the clearly marked example entries that must be replaced."""
        return "REPLACE" in (self.slug + self.url).upper()


class TitleFilter(_Strict):
    include: list[str] = []
    exclude: list[str] = []


class LocationFilter(_Strict):
    include: list[str] = []
    remote: Literal["required", "preferred", "any", "excluded"] = "any"


class CompanyInfo(_Strict):
    domain: str = ""
    pages: list[str] = []


class SearchConfig(_Strict):
    sources: list[SourceSpec] = []
    titles: TitleFilter = TitleFilter()
    locations: LocationFilter = LocationFilter()
    max_age_days: int = Field(default=30, ge=1)
    companies: dict[str, CompanyInfo] = {}


class Weights(_Strict):
    must_have: float = Field(default=0.30, ge=0)
    nice_to_have: float = Field(default=0.10, ge=0)
    semantic: float = Field(default=0.20, ge=0)
    title: float = Field(default=0.10, ge=0)
    seniority: float = Field(default=0.10, ge=0)
    location: float = Field(default=0.10, ge=0)
    language: float = Field(default=0.05, ge=0)
    salary: float = Field(default=0.05, ge=0)

    def normalised(self) -> dict[str, float]:
        """Return weights scaled to sum to 1."""
        raw = self.model_dump()
        total = sum(raw.values()) or 1.0
        return {k: v / total for k, v in raw.items()}


class SalaryFloor(_Strict):
    amount: int | None = None
    currency: str = "EUR"


class Dealbreakers(_Strict):
    excluded_companies: list[str] = []
    excluded_keywords: list[str] = []
    require_language_match: bool = True
    enforce_salary_floor: bool = False


class PreferenceLearning(_Strict):
    enabled: bool = True
    max_adjustment: float = Field(default=10.0, ge=0, le=50)


Seniority = Literal["intern", "junior", "mid", "senior", "staff", "principal", "lead", "unknown"]


class CriteriaConfig(_Strict):
    weights: Weights = Weights()
    threshold: float = Field(default=50.0, ge=0, le=100)
    top_n: int = Field(default=8, ge=1)
    related_skill_credit: float = Field(default=0.5, ge=0, le=1)
    target_seniority: list[Seniority] = ["mid", "senior"]
    salary_floor: SalaryFloor = SalaryFloor()
    dealbreakers: Dealbreakers = Dealbreakers()
    preference: PreferenceLearning = PreferenceLearning()


class LanguageSkill(_Strict):
    code: str
    level: Literal["native", "fluent", "professional", "intermediate", "basic"] = "professional"


class Identity(_Strict):
    name: str
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: dict[str, str] = {}
    languages: list[LanguageSkill] = []


class Role(_Strict):
    employer: str
    title: str
    start: str
    end: str = "present"
    location: str = ""


class Degree(_Strict):
    institution: str
    degree: str
    field: str = ""
    start: str = ""
    end: str = ""


class DocumentsSpec(_Strict):
    dir: str = "profiles/me"
    include: list[str] = ["*.pdf", "*.md", "*.txt", "*.tex"]
    evidence_file: str = "evidence.yaml"


class GitHubSpec(_Strict):
    username: str | None = None
    max_repos: int = Field(default=10, ge=0, le=100)
    readme_max_chars: int = Field(default=3000, ge=0)


class ProfileConfig(_Strict):
    identity: Identity
    experience: list[Role] = []
    education: list[Degree] = []
    documents: DocumentsSpec = DocumentsSpec()
    github: GitHubSpec = GitHubSpec()


class SkillsConfig(_Strict):
    aliases: dict[str, list[str]] = {}
    related: dict[str, list[str]] = {}


class ModelPrice(_Strict):
    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None

    @property
    def is_set(self) -> bool:
        """Prices are usable only if input and output are both filled in."""
        return self.input_per_mtok is not None and self.output_per_mtok is not None


class PricingConfig(_Strict):
    currency: str = "USD"
    models: dict[str, ModelPrice] = {}


_FIXES: dict[str, str] = {
    "extra_forbidden": "unknown key: remove it or fix the spelling (see comments in the file)",
    "missing": "this key is required: add it (see the example file in config/)",
    "literal_error": "use one of the allowed values listed in the comment above this key",
}


def load_yaml_model[M: BaseModel](path: Path, model: type[M]) -> M:
    """Parse a YAML file into a strict pydantic model, raising ConfigErrors with fixes."""
    shown = _display(path)
    if not path.exists():
        raise ConfigErrors(
            [ConfigError(shown, "(file)", "file not found", "run `make init` or restore it")]
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark else "(parse)"
        raise ConfigErrors(
            [ConfigError(shown, where, "invalid YAML", "check indentation and quoting")]
        ) from None
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        errors = [
            ConfigError(
                shown,
                ".".join(str(p) for p in err["loc"]) or "(root)",
                err["msg"],
                _FIXES.get(err["type"], "see the comment above this key in the file"),
            )
            for err in exc.errors()
        ]
        raise ConfigErrors(errors) from None


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class AppConfig:
    """All validated config for one process."""

    settings: Settings
    search: SearchConfig
    criteria: CriteriaConfig
    profile: ProfileConfig
    skills: SkillsConfig
    pricing: PricingConfig


def load_app_config(settings: Settings | None = None) -> AppConfig:
    """Load settings plus every YAML file, collecting all errors before raising."""
    settings = settings or load_settings()
    cfg_dir = settings.resolve(settings.config_dir)
    specs: list[tuple[str, Path, type[BaseModel]]] = [
        ("search", settings.search_config_path, SearchConfig),
        ("criteria", cfg_dir / "criteria.yaml", CriteriaConfig),
        ("profile", settings.profile_config_path, ProfileConfig),
        ("skills", cfg_dir / "skills.yaml", SkillsConfig),
        ("pricing", cfg_dir / "pricing.yaml", PricingConfig),
    ]
    loaded: dict[str, BaseModel] = {}
    errors: list[ConfigError] = []
    for name, path, model in specs:
        try:
            loaded[name] = load_yaml_model(path, model)
        except ConfigErrors as exc:
            errors.extend(exc.errors)
    if errors:
        raise ConfigErrors(errors)
    return AppConfig(settings=settings, **loaded)  # type: ignore[arg-type]


@functools.cache
def cached_app_config() -> AppConfig:
    """Process-wide config for the UI (the CLI loads explicitly)."""
    return load_app_config()
