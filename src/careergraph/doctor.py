"""`make doctor`: an OK/WARN/FAIL checklist with the next action for each item."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import create_engine, text

from careergraph.config import (
    REPO_ROOT,
    AppConfig,
    ConfigErrors,
    Settings,
    load_app_config,
    load_settings,
)
from careergraph.latex.compile import detect_engine

Status = Literal["OK", "WARN", "FAIL"]
DOC_SUFFIXES = {".pdf", ".md", ".txt", ".tex"}


@dataclass(frozen=True)
class Check:
    """One doctor line."""

    name: str
    status: Status
    detail: str
    action: str = ""


def run_checks(settings: Settings | None = None) -> list[Check]:
    """Run every check. Never raises: problems become FAIL lines."""
    checks: list[Check] = []
    env_file = REPO_ROOT / ".env"
    checks.append(
        Check(".env", "OK", "found")
        if env_file.exists()
        else Check(".env", "WARN", "missing; using defaults (demo mode)", "run `make init`")
    )
    try:
        settings = settings or load_settings()
    except ConfigErrors as exc:
        return [*checks, Check("settings", "FAIL", exc.render(), "fix .env as shown")]
    checks.append(Check("mode", "OK", f"APP_MODE={settings.app_mode}, APP_ENV={settings.app_env}"))
    try:
        cfg = load_app_config(settings)
        checks.append(Check("config", "OK", "all YAML files valid"))
    except ConfigErrors as exc:
        return [*checks, Check("config", "FAIL", exc.render(), "fix the keys listed above")]
    checks += _model_checks(settings)
    checks += _network_checks(settings, cfg)
    checks.append(_latex_check(settings))
    checks.append(_db_check(settings))
    checks.append(_profile_check(settings, cfg))
    checks.append(_spend_check(settings, cfg))
    checks.append(_ui_check(settings))
    return checks


def _model_checks(s: Settings) -> list[Check]:
    if s.is_demo:
        return [Check("models", "OK", "demo mode uses the built-in fake LLM; no keys needed")]
    out: list[Check] = []
    for tier, model in (("cheap", s.cheap_model), ("strong", s.strong_model)):
        provider = model.split(":", 1)[0]
        if provider == "anthropic":
            ok = s.anthropic_api_key is not None
            out.append(
                Check(
                    f"model:{tier}",
                    "OK" if ok else "FAIL",
                    f"{model} ({'key set' if ok else 'ANTHROPIC_API_KEY missing'})",
                    "" if ok else "set ANTHROPIC_API_KEY in .env",
                )
            )
        else:
            out.append(
                Check(
                    f"model:{tier}",
                    "WARN",
                    f"{model}: provider key not checked (only anthropic is verified)",
                    "set the provider's API key env var per LangChain docs",
                )
            )
    return out


def _network_checks(s: Settings, cfg: AppConfig) -> list[Check]:
    out: list[Check] = []
    if not s.is_demo:
        active = [x for x in cfg.search.sources if x.enabled]
        placeholders = [x for x in active if x.is_placeholder]
        if not active:
            out.append(
                Check(
                    "sources",
                    "WARN",
                    "no enabled sources in config/search.yaml",
                    "add Greenhouse/Lever/Ashby slugs or RSS URLs and set enabled: true",
                )
            )
        elif placeholders:
            out.append(
                Check(
                    "sources",
                    "WARN",
                    f"{len(placeholders)} placeholder source(s) will be skipped",
                    "replace REPLACE_WITH_* values in config/search.yaml",
                )
            )
        else:
            out.append(Check("sources", "OK", f"{len(active)} enabled source(s)"))
        gh = cfg.profile.github.username
        if gh and s.github_token is None:
            out.append(
                Check(
                    "github",
                    "WARN",
                    "no GITHUB_TOKEN: 60 requests/hour limit",
                    "optional: set GITHUB_TOKEN (no scopes needed)",
                )
            )
        else:
            out.append(
                Check("github", "OK", "token set" if gh else "no GitHub username configured")
            )
    if s.enable_company_research and s.search_provider != "site":
        key = s.tavily_api_key if s.search_provider == "tavily" else s.brave_api_key
        ok = key is not None or s.is_demo
        out.append(
            Check(
                "search",
                "OK" if ok else "FAIL",
                f"SEARCH_PROVIDER={s.search_provider}",
                ""
                if ok
                else f"set {s.search_provider.upper()}_API_KEY or use SEARCH_PROVIDER=site",
            )
        )
    return out


def _latex_check(s: Settings) -> Check:
    engine = detect_engine(s.latex_engine)
    if engine:
        return Check("latex", "OK", f"engine: {engine}")
    if s.latex_engine == "none":
        return Check("latex", "OK", "compilation disabled; .tex files only")
    return Check(
        "latex",
        "WARN",
        "no tectonic/pdflatex found; .tex files only",
        "optional: install tectonic, or use the Docker `latex` target",
    )


def _db_check(s: Settings) -> Check:
    try:
        if not s.is_postgres:
            s.resolve(s.data_dir).mkdir(parents=True, exist_ok=True)
        engine = create_engine(s.db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        kind = "postgres" if s.is_postgres else "sqlite"
        return Check("database", "OK", f"{kind} reachable")
    except Exception as exc:
        return Check(
            "database",
            "FAIL",
            f"cannot connect: {type(exc).__name__}: {exc}",
            "check DATABASE_URL (empty = local SQLite)",
        )


def _profile_check(s: Settings, cfg: AppConfig) -> Check:
    if s.is_demo:
        return Check("profile", "OK", "demo profile: Sam Demo (fictional)")
    doc_dir = s.resolve(Path(cfg.profile.documents.dir))
    docs = (
        [p for p in doc_dir.glob("*") if p.suffix.lower() in DOC_SUFFIXES]
        if doc_dir.exists()
        else []
    )
    if cfg.profile.identity.name.strip().lower() == "your name":
        return Check(
            "profile",
            "FAIL",
            "config/profile.yaml still has the placeholder name",
            "fill identity, experience and education in config/profile.yaml",
        )
    if not docs and not cfg.profile.github.username:
        return Check(
            "profile",
            "FAIL",
            f"no documents in {doc_dir} and no GitHub username",
            "put your CV (.pdf/.md/.txt/.tex) in profiles/me/ (`make init` creates it)",
        )
    return Check("profile", "OK", f"{len(docs)} document(s) in {doc_dir.name}/")


def _spend_check(s: Settings, cfg: AppConfig) -> Check:
    caps = f"tokens: <= {s.max_tokens_per_run:,}/run, <= {s.max_tokens_per_day:,}/day"
    if s.is_demo:
        return Check("spend", "OK", f"demo mode spends nothing ({caps}, enforced on fake tokens)")
    prices = [cfg.pricing.models.get(m) for m in (s.cheap_model, s.strong_model)]
    usable = [p for p in prices if p is not None and p.is_set]
    if not usable:
        return Check(
            "spend",
            "WARN",
            f"{caps}; USD unknown (config/pricing.yaml is empty)",
            "copy current prices from your provider into config/pricing.yaml",
        )
    worst_rate = max(max(p.input_per_mtok or 0, p.output_per_mtok or 0) for p in usable)
    per_run = s.max_tokens_per_run / 1e6 * worst_rate
    per_day = s.max_tokens_per_day / 1e6 * worst_rate
    return Check(
        "spend",
        "OK",
        f"{caps}; worst case <= ${per_run:.2f}/run, <= ${per_day:.2f}/day "
        "(all tokens billed at the highest configured rate)",
    )


def _ui_check(s: Settings) -> Check:
    if s.app_env == "production" and s.ui_password is None:
        return Check("ui", "FAIL", "APP_ENV=production without UI_PASSWORD", "set UI_PASSWORD")
    exposed = s.ui_host not in ("127.0.0.1", "localhost")
    if exposed and s.ui_password is None:
        return Check("ui", "WARN", f"UI binds {s.ui_host} without a password", "set UI_PASSWORD")
    return Check("ui", "OK", f"binds {s.ui_host}:{s.ui_port}")
