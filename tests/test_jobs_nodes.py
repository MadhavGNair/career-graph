"""find_jobs + extract_jobs as a small graph: Send fan-out, reducers, hash skip, cap."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from careergraph.graphs.job_search.nodes.extract_jobs import extract_jobs
from careergraph.graphs.job_search.nodes.find_jobs import find_jobs
from careergraph.graphs.job_search.routing import fan_out_postings
from careergraph.graphs.job_search.state import JobBranch, JobSearchState
from careergraph.service.wiring import Services
from tests.helpers import demo_services


def _noop(state: JobSearchState) -> dict[str, Any]:
    return {}


def _graph() -> Any:
    g = StateGraph(JobSearchState, context_schema=Services)
    g.add_node("find_jobs", find_jobs)
    g.add_node("extract_jobs", cast(Any, extract_jobs), input_schema=JobBranch)
    g.add_node("match_jobs", _noop)
    g.add_edge(START, "find_jobs")
    g.add_conditional_edges("find_jobs", fan_out_postings, ["extract_jobs", "match_jobs"])
    g.add_edge("extract_jobs", "match_jobs")
    g.add_edge("match_jobs", END)
    return g.compile()


def test_fan_out_analyses_every_new_posting_then_reuses_hashes(tmp_path: Path) -> None:
    svc = demo_services(tmp_path)
    out = _graph().invoke({"run_id": "r1"}, context=svc)
    f = out["funnel"]
    assert (f["fetched"], f["after_title"], f["after_age"], f["new"]) == (30, 26, 25, 23)
    assert len(f["duplicates"]) == 2
    assert len(out["analyses"]) == 23
    flagged = {k for k, v in out["analyses"].items() if v.injection_flag}
    assert len(flagged) == 3
    tokens_first = svc.repo.run_totals("r1")[0]
    assert tokens_first > 0
    again = _graph().invoke({"run_id": "r2"}, context=svc)
    assert again["funnel"]["cached"] == 23 and again["funnel"]["new"] == 0
    assert len(again["analyses"]) == 23
    assert svc.repo.run_totals("r2") == (0, 0.0)


def test_max_jobs_per_run_caps_new_analyses(tmp_path: Path) -> None:
    svc = demo_services(tmp_path, max_jobs_per_run=5)
    out = _graph().invoke({"run_id": "r1"}, context=svc)
    assert len(out["analyses"]) == 5 and out["funnel"]["skipped_over_cap"] == 18


def test_failing_source_does_not_stop_the_run(tmp_path: Path) -> None:
    import httpx

    from careergraph.sources.fixtures import FixtureTransport

    class Broken(FixtureTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.ashbyhq.com":
                return httpx.Response(500)
            return super().handle_request(request)

    from careergraph.config import load_app_config
    from careergraph.service.wiring import build_services
    from tests.conftest import make_settings

    svc = build_services(load_app_config(make_settings(tmp_path)), transport=Broken())
    out = _graph().invoke({"run_id": "r"}, context=svc)
    assert set(out["funnel"]["source_errors"]) == {"ashby:orbitly", "ashby:lumen-legal"}
    assert out["funnel"]["fetched"] == 23
