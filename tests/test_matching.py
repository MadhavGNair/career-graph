"""Scoring criteria, dealbreakers, partial credit, shortlist and preference learning."""

from __future__ import annotations

from pathlib import Path

from langgraph.store.memory import InMemoryStore

from careergraph.config import AppConfig, load_app_config
from careergraph.domain.models import (
    AnalyzedJob,
    EvidenceItem,
    InjectionReport,
    JobAnalysis,
    JobPosting,
    ProfileSnapshot,
    ReasonTag,
    Salary,
    ShortlistDecision,
)
from careergraph.matching.payload import parse_decisions
from careergraph.matching.scoring import ScoringContext, score_job, seniority_fit, shortlist
from careergraph.memory import preferences
from careergraph.retrieval.embeddings import HashingEmbedder
from careergraph.retrieval.index import HybridIndex
from careergraph.skills import SkillNormalizer
from tests.conftest import make_settings


def _cfg(tmp_path: Path) -> AppConfig:
    return load_app_config(make_settings(tmp_path))


def _job(**kw: object) -> AnalyzedJob:
    posting = JobPosting(id=str(kw.get("id", "j1")), source="greenhouse", company=str(kw.get("company", "Acme")),
                         title=str(kw.get("title", "Senior Machine Learning Engineer")),
                         location=str(kw.get("location", "Berlin, Germany")), description=str(kw.get("text", "x")))  # fmt: skip
    analysis = JobAnalysis(
        summary="s",
        must_have=list(kw.get("must", ["python", "tensorflow"])),  # type: ignore[call-overload]
        nice_to_have=list(kw.get("nice", [])),  # type: ignore[call-overload]
        seniority=kw.get("seniority", "senior"),  # type: ignore[arg-type]
        remote=kw.get("remote", "hybrid"),  # type: ignore[arg-type]
        languages=list(kw.get("languages", ["en"])),  # type: ignore[call-overload]
        salary=kw.get("salary"),  # type: ignore[arg-type]
    )
    return AnalyzedJob(
        posting=posting, analysis=analysis, injection=InjectionReport(flagged=False, score=0)
    )


def _ctx(cfg: AppConfig) -> ScoringContext:
    ev = [
        EvidenceItem(id="ev-001", kind="experience", text="Built PyTorch models in Python", skills=["python", "pytorch"], source_ref="cv"),
    ]  # fmt: skip
    snap = ProfileSnapshot(evidence=ev, skills={"python": ["ev-001"], "pytorch": ["ev-001"]})
    return ScoringContext(
        cfg,
        snap,
        HybridIndex([(e.id, e.text) for e in ev], HashingEmbedder()),
        SkillNormalizer(cfg.skills),
    )


def test_partial_credit_via_related_skill(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    r = score_job(_job(), _ctx(cfg), 0.0)
    tf = next(s for s in r.skills if s.skill == "tensorflow")
    assert tf.status == "partial" and tf.via == "pytorch" and tf.evidence_ids == ["ev-001"]
    must = next(c for c in r.breakdown if c.name == "must_have")
    assert must.score == (1 + cfg.criteria.related_skill_credit) / 2
    assert abs(sum(c.weight for c in r.breakdown) - 1) < 1e-3


def test_dealbreakers(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    ctx = _ctx(cfg)
    assert any(
        "unpaid" in d for d in score_job(_job(text="An unpaid trial week."), ctx, 0).dealbreakers
    )
    fr = score_job(_job(languages=["fr"]), ctx, 0)
    assert any("language" in d for d in fr.dealbreakers)
    de = score_job(_job(languages=["de"]), ctx, 0)  # Sam speaks German at intermediate level
    assert (
        not de.dealbreakers and next(c for c in de.breakdown if c.name == "language").score == 0.5
    )


def test_salary_floor_and_unknown_salary(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    crit = cfg.criteria.model_copy(update={
        "salary_floor": cfg.criteria.salary_floor.model_copy(update={"amount": 80000}),
        "dealbreakers": cfg.criteria.dealbreakers.model_copy(update={"enforce_salary_floor": True}),
    })  # fmt: skip
    ctx = _ctx(AppConfig(**{**cfg.__dict__, "criteria": crit}))
    low = score_job(_job(salary=Salary(min=50000, max=60000, currency="EUR")), ctx, 0)
    assert "salary below your floor" in low.dealbreakers
    assert not score_job(_job(), ctx, 0).dealbreakers  # unknown salary never penalised


def test_seniority_fit_levels() -> None:
    assert seniority_fit("senior", ["senior"]) == 1.0
    assert seniority_fit("junior", ["mid"]) == 0.5
    assert seniority_fit("principal", ["mid", "senior"]) == 0.0
    assert seniority_fit("lead", ["staff"]) == 1.0


def test_preference_adjustment_is_clipped(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    r = score_job(_job(), _ctx(cfg), 999.0)
    assert r.preference_adjustment == cfg.criteria.preference.max_adjustment


def test_shortlist_threshold_topn_and_dealbreakers(tmp_path: Path) -> None:
    ctx = _ctx(_cfg(tmp_path))
    a = score_job(_job(id="a"), ctx, 0)
    b = score_job(_job(id="b", text="unpaid"), ctx, 0)
    assert shortlist([a, b], threshold=0, top_n=5) == ["a"]
    assert shortlist([a], threshold=101, top_n=5) == []


def test_learning_from_tags_changes_future_scores(tmp_path: Path) -> None:
    store = InMemoryStore()
    junior = _job(id="jr", seniority="junior", title="Junior Data Scientist")
    approved = _job(id="ok", company="Good Co")
    preferences.learn(store, [
        ShortlistDecision(job_id="jr", decision="reject", reason_tags=[ReasonTag.TOO_JUNIOR]),
        ShortlistDecision(job_id="ok", decision="approve"),
        ShortlistDecision(job_id="x", decision="defer"),
    ], {"jr": junior, "ok": approved})  # fmt: skip
    w = preferences.load(store)
    assert w["seniority:junior"] == -1.0 and w["company:good co"] == 0.5
    another_junior = _job(id="jr2", seniority="junior", company="Other")
    same_but_senior = _job(id="sr2", seniority="senior", company="Other")
    gap = preferences.adjustment(w, same_but_senior) - preferences.adjustment(w, another_junior)
    assert gap == preferences.POINTS_PER_UNIT * 1.5  # +0.5 senior (approved) - (-1.0) junior


def test_parse_decisions_defaults_and_validation() -> None:
    out = parse_decisions(
        [{"job_id": "a", "decision": "approve"}, {"job_id": "zzz", "decision": "approve"},
         {"job_id": "b", "decision": "maybe"}],
        ["a", "b"],
    )  # fmt: skip
    assert [(d.job_id, d.decision) for d in out] == [("a", "approve"), ("b", "defer")]
