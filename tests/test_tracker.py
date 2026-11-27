"""Tracker graph: validated transitions, router on status, interview prep and the mock
interview loop with one interrupt per turn."""

from __future__ import annotations

from pathlib import Path

import pytest

from careergraph.domain.models import ReviewAction, ShortlistDecision
from careergraph.service.api import CareerGraphService
from tests.helpers import demo_service

GOOD = ("At Quillfeather the situation was a fragile cron-based pipeline. My task was to make "
        "Kubernetes deployments reliable for 35 models. I designed an MLflow and Airflow platform, "
        "wrote the deployment tooling and ran the rollout. The result was release time cut from two "
        "weeks to one day, and training costs reduced by 38%. " * 2)  # fmt: skip


@pytest.fixture
def ready_app(tmp_path: Path) -> tuple[CareerGraphService, str]:
    svc = demo_service(tmp_path, enable_company_research=True)
    out = svc.start_run()
    job = out.payload["items"][0]["job_id"]  # type: ignore[index]
    out = svc.approve_shortlist(out.thread_id, [ShortlistDecision(job_id=job, decision="approve")])
    out = svc.review_documents(
        out.thread_id, [ReviewAction(job_id=job, action="approve", override=True)]
    )
    assert out.status == "completed"
    return svc, job


def test_invalid_transition_is_refused(ready_app: tuple[CareerGraphService, str]) -> None:
    svc, job = ready_app
    out = svc.change_status(job, "offer")
    assert out.status == "completed" and "No change" in out.summary
    assert svc.repo.get_application(job).status == "ready"  # type: ignore[union-attr]


def test_status_router_and_mock_interview(ready_app: tuple[CareerGraphService, str]) -> None:
    svc, job = ready_app
    assert svc.change_status(job, "applied").status == "completed"
    out = svc.change_status(job, "interview")
    assert out.status == "waiting_mock_interview" and out.payload
    assert out.payload["turn"] == 1 and out.payload["question"]["kind"] == "technical"
    state = svc.tracker_graph.get_state(svc._config(out.thread_id)).values
    prep = state["prep"]
    assert prep.questions and prep.stories and prep.research is not None
    evidence_ids = {e.id for e in svc.repo.latest_profile().evidence}  # type: ignore[union-attr]
    assert all(set(s.evidence_ids) <= evidence_ids for s in prep.stories)
    assert [p.waiting_for for p in svc.list_pending()] == ["mock_interview"]

    good = svc.answer_mock(out.thread_id, GOOD)
    assert good.status == "waiting_mock_interview" and good.payload["turn"] == 2  # type: ignore[index]
    weak = svc.answer_mock(out.thread_id, "I don't know.")
    assert weak.status == "waiting_mock_interview"
    done = svc.answer_mock(out.thread_id, "/stop")
    assert done.status == "completed" and "Mock interview: 3 answers" in done.summary
    turns = svc.tracker_graph.get_state(svc._config(out.thread_id)).values["transcript"]
    assert turns[0].score.overall > turns[1].score.overall
    assert svc.repo.get_application(job).status == "interview"  # type: ignore[union-attr]
    svc.close()
