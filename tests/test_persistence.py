"""Checkpoint serializer allowlist, DB schema version, status transitions."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from careergraph.domain.models import JobPosting, ReasonTag, ShortlistDecision
from careergraph.domain.status import ApplicationStatus, InvalidTransition, check_transition
from careergraph.persistence.checkpoint import domain_types, make_serializer
from careergraph.persistence.db import SCHEMA_VERSION, SchemaVersion, make_engine
from careergraph.persistence.repository import Repository


class NotRegistered(BaseModel):
    x: int = 1


def test_domain_types_roundtrip_under_allowlist() -> None:
    serde = make_serializer()
    objs = [
        JobPosting(id="a", source="rss", company="c", title="t", description="d"),
        ShortlistDecision(job_id="a", decision="reject", reason_tags=[ReasonTag.SALARY]),
    ]
    for obj in objs:
        back = serde.loads_typed(serde.dumps_typed(obj))
        assert back == obj and type(back) is type(obj)
    assert JobPosting in domain_types() and ReasonTag in domain_types()


def test_unregistered_types_are_not_reconstructed() -> None:
    serde = make_serializer()
    back = serde.loads_typed(serde.dumps_typed(NotRegistered()))
    assert not isinstance(back, NotRegistered)


def test_schema_version_recorded(tmp_path: Path) -> None:
    repo = Repository(make_engine(f"sqlite:///{tmp_path / 'x.db'}"))
    with Session(repo.engine) as s:
        assert s.get(SchemaVersion, SCHEMA_VERSION) is not None


def test_status_transitions() -> None:
    check_transition(ApplicationStatus.READY, ApplicationStatus.APPLIED)
    with pytest.raises(InvalidTransition, match="allowed"):
        check_transition(ApplicationStatus.READY, ApplicationStatus.OFFER)
    with pytest.raises(InvalidTransition, match="terminal"):
        check_transition(ApplicationStatus.REJECTED, ApplicationStatus.APPLIED)
