"""research_company subgraph on fixtures: cited sources only, domain allowlist, limits."""

from __future__ import annotations

from pathlib import Path

from careergraph.graphs.job_search.subgraphs.research_company import RESEARCH_COMPANY
from tests.helpers import demo_services


def _run(tmp_path: Path, company: str, domains: list[str], **kw: object):  # type: ignore[no-untyped-def]
    svc = demo_services(tmp_path, **kw)
    return RESEARCH_COMPANY.invoke(
        {
            "messages": [],
            "run_id": "r",
            "company": company,
            "allowed_domains": domains,
            "steps": 0,
            "tokens": 0,
        },
        context=svc,
    )


def test_site_provider_brief_cites_only_read_pages(tmp_path: Path) -> None:
    out = _run(tmp_path, "Nimbus Analytics", ["nimbus-analytics.example"])
    brief = out["brief"]
    read = {
        "https://nimbus-analytics.example/about",
        "https://nimbus-analytics.example/engineering",
    }
    assert brief.facts and {f.source_url for f in brief.facts} <= read
    assert brief.confidence == "high" and brief.steps_used >= 2


def test_tavily_fixture_respects_robots_and_allowlist(tmp_path: Path) -> None:
    out = _run(tmp_path, "Nimbus Analytics", ["nimbus-analytics.example"], search_provider="tavily")
    fetched = [m.content for m in out["messages"] if getattr(m, "name", "") == "fetch_page"]
    assert fetched and all("private" not in str(c) or "robots" in str(c) for c in fetched)


def test_disallowed_domain_is_not_fetched(tmp_path: Path) -> None:
    out = _run(tmp_path, "Kestrel Health", [])  # no company domain configured for research
    fetched = [str(m.content) for m in out["messages"] if getattr(m, "name", "") == "fetch_page"]
    assert all("domain not allowed" in c for c in fetched)
    assert out["brief"].facts == [] and out["brief"].confidence == "low"


def test_injection_in_page_is_flagged(tmp_path: Path) -> None:
    out = _run(tmp_path, "Kestrel Health", ["kestrel-health.example"])
    pages = [str(m.content) for m in out["messages"] if getattr(m, "name", "") == "fetch_page"]
    assert any('"injection_flag": true' in p for p in pages)


def test_step_limit(tmp_path: Path) -> None:
    out = _run(tmp_path, "Nimbus Analytics", ["nimbus-analytics.example"], research_max_steps=1)
    assert out["steps"] == 1 and "step limit" in out["brief"].stopped_reason
