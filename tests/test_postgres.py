"""Postgres backend (app DB + PostgresSaver + PostgresStore). Opt-in: set
CAREERGRAPH_TEST_POSTGRES_URL to an empty, disposable database, e.g.
postgresql://careergraph:careergraph@127.0.0.1:55432/careergraph"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from careergraph.domain.models import ShortlistDecision
from tests.helpers import demo_service

URL = os.environ.get("CAREERGRAPH_TEST_POSTGRES_URL", "")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="CAREERGRAPH_TEST_POSTGRES_URL not set"),
]


def test_pause_resume_and_store_on_postgres(tmp_path: Path) -> None:
    svc = demo_service(tmp_path, database_url=URL)
    assert svc.persistence == "postgres"
    out = svc.start_run()
    assert out.status == "waiting_shortlist"
    tid, first = out.thread_id, out.payload["items"][0]["job_id"]  # type: ignore[index]
    svc.close()
    svc2 = demo_service(tmp_path, database_url=URL)
    assert tid in [p.thread_id for p in svc2.list_pending()]
    done = svc2.approve_shortlist(tid, [ShortlistDecision(job_id=first, decision="approve")])
    assert done.status == "waiting_review"
    assert svc2.store.search(("preferences", "default"), limit=5)
    assert len(svc2.history(tid)) > 5
    svc2.close()
