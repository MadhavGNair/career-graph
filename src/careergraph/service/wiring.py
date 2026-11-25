"""Build the runtime services (LangGraph runtime context) for demo or live mode.

This is the ONLY place where demo and live differ: the fetch transport and resolver, the
model factory's fake/live choice, the clock and the embedding backend. Graph code is shared.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml

from careergraph.config import DEMO_DIR, AppConfig, Settings
from careergraph.llm.budget import Budget
from careergraph.llm.factory import ModelFactory
from careergraph.persistence.db import make_engine
from careergraph.persistence.repository import Repository
from careergraph.retrieval.embeddings import Embedder, make_embedder
from careergraph.security.fetcher import FetchPolicy, SafeFetcher, system_resolver
from careergraph.skills import SkillNormalizer
from careergraph.sources.fixtures import FixtureTransport, demo_resolver
from careergraph.sources.github import GitHubAdapter
from careergraph.sources.websearch import (
    BraveProvider,
    SearchProvider,
    SiteProvider,
    TavilyProvider,
)


@dataclass
class Services:
    """Everything nodes need, passed as LangGraph runtime context (never checkpointed)."""

    cfg: AppConfig
    repo: Repository
    models: ModelFactory
    skills: SkillNormalizer
    fetcher: SafeFetcher
    github: GitHubAdapter
    search: SearchProvider
    embedder: Embedder
    today: date
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def settings(self) -> Settings:
        """Shortcut to process settings."""
        return self.cfg.settings


def demo_today() -> date:
    """The fixed demo date from data/demo/manifest.yaml."""
    manifest = yaml.safe_load((DEMO_DIR / "manifest.yaml").read_text())
    return date.fromisoformat(str(manifest["today"]))


def _secret(value: Any, demo: bool) -> str:
    if value is not None:
        return str(value.get_secret_value())
    return "demo-key" if demo else ""


def build_services(
    cfg: AppConfig,
    repo: Repository | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Services:
    """Wire services for the configured mode."""
    s = cfg.settings
    demo = s.is_demo
    repo = repo or Repository(make_engine(s.db_url))
    policy = FetchPolicy(
        max_bytes=s.http_max_bytes,
        timeout=s.http_timeout_seconds,
        min_interval=0.0 if demo else s.http_min_interval_seconds,
        contact=s.http_contact,
    )
    cache_dir: Path = s.resolve(s.cache_dir)
    fetcher = SafeFetcher(
        policy,
        cache_dir=cache_dir,
        transport=transport or (FixtureTransport() if demo else None),
        resolver=demo_resolver if demo else system_resolver,
    )
    fetcher.allow(info.domain for info in cfg.search.companies.values())
    skills = SkillNormalizer(cfg.skills)
    search: SearchProvider
    if s.search_provider == "tavily":
        search = TavilyProvider(fetcher, _secret(s.tavily_api_key, demo))
    elif s.search_provider == "brave":
        search = BraveProvider(fetcher, _secret(s.brave_api_key, demo))
    else:
        search = SiteProvider(cfg.search)
    token = s.github_token.get_secret_value() if s.github_token else None
    return Services(
        cfg=cfg,
        repo=repo,
        models=ModelFactory(s, Budget(s, cfg.pricing, repo), skills),
        skills=skills,
        fetcher=fetcher,
        github=GitHubAdapter(fetcher, token),
        search=search,
        embedder=make_embedder(s.effective_embedding_backend, s.embedding_model, cache_dir),
        today=demo_today() if demo else date.today(),
    )
