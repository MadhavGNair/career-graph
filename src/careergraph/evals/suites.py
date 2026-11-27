"""Eval suites. Each returns metrics in [0, 1] plus per-item details.

Fake mode runs the deterministic fake LLM: it verifies the PIPELINE (parsing, normalisation,
routing, scoring, verification plumbing), not model quality. Live mode runs the configured
real models on the same fictional fixtures (it costs tokens; budgets still apply).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from careergraph.config import DEMO_DIR, AppConfig, Settings, load_app_config
from careergraph.domain.models import Claim, Entailment, EvidenceItem, JobAnalysis, JobPosting
from careergraph.graphs.job_search.graph import build_jobs_graph
from careergraph.llm.budget import Budget
from careergraph.llm.factory import ModelFactory
from careergraph.llm.prompts import (
    EXTRACT_JOB_SYSTEM,
    VERIFY_SYSTEM,
    extract_job_prompt,
    verify_prompt,
)
from careergraph.matching.scoring import ScoringContext, score_job
from careergraph.memory import preferences
from careergraph.persistence.repository import Repository
from careergraph.retrieval.index import HybridIndex
from careergraph.security.injection import scan
from careergraph.service.wiring import Services, build_services
from careergraph.sources.jobs.factory import build_sources

GOLD = DEMO_DIR / "evals"
Mode = Literal["fake", "live"]
SUITES = ("match", "extraction", "verifier", "injection")


@dataclass
class SuiteResult:
    """Metrics, thresholds and details of one suite run."""

    suite: str
    mode: str
    metrics: dict[str, float]
    thresholds: dict[str, float]
    details: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[str]:
        """Metrics below their threshold."""
        return [k for k, v in self.thresholds.items() if self.metrics.get(k, 0.0) < v]

    @property
    def passed(self) -> bool:
        """True when every gated metric meets its threshold."""
        return not self.failures


def load_thresholds() -> dict[str, dict[str, float]]:
    """Gates from data/demo/evals/thresholds.yaml."""
    return yaml.safe_load((GOLD / "thresholds.yaml").read_text()) or {}


def eval_services(base: Settings, mode: Mode, workdir: Path) -> Services:
    """Fixture data in an isolated temp dir; real models only when mode == live."""
    demo = base.model_copy(
        update={
            "app_mode": "demo",
            "data_dir": workdir / "data",
            "cache_dir": workdir / "cache",
            "output_dir": workdir / "out",
            "database_url": "",
            "latex_engine": "none",
            "enable_company_research": False,
        }
    )
    svc = build_services(load_app_config(demo))
    if mode == "live":
        live = demo.model_copy(update={"app_mode": "live"})
        svc.models = ModelFactory(live, Budget(live, svc.cfg.pricing, svc.repo), svc.skills)
    return svc


def _fixture_postings(svc: Services) -> dict[str, JobPosting]:
    sources, _ = build_sources(svc.cfg.search, svc.fetcher)
    return {p.id: p for s in sources for p in s.fetch()}


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def extraction_suite(svc: Services, mode: Mode) -> SuiteResult:
    """Extracted must+nice skills vs hand-written gold, micro-averaged."""
    gold: dict[str, dict[str, list[str]]] = yaml.safe_load(
        (GOLD / "expected_skills.yaml").read_text()
    )
    postings = _fixture_postings(svc)
    llm = svc.models.get_model("cheap")
    tp = fp = fn = 0
    details = []
    for pid, want in sorted(gold.items()):
        p = postings[pid]
        a = llm.structured(
            task="extract_job",
            schema=JobAnalysis,
            system=EXTRACT_JOB_SYSTEM,
            prompt=extract_job_prompt(p),
            payload={"posting": p.model_dump(mode="json")},
            run_id=f"eval-extraction-{mode}",
        )
        got = set(svc.skills.normalize_all(a.must_have + a.nice_to_have))
        exp = set(want["must_have"] + want["nice_to_have"])
        tp, fp, fn = tp + len(got & exp), fp + len(got - exp), fn + len(exp - got)
        details.append({"id": pid, "missing": sorted(exp - got), "extra": sorted(got - exp)})
    p, r, f1 = _prf(tp, fp, fn)
    return SuiteResult(
        "extraction",
        mode,
        {"skills_precision": p, "skills_recall": r, "skills_f1": f1},
        {},
        details,
    )


def injection_suite(svc: Services, mode: Mode) -> SuiteResult:
    """Heuristic scanner vs labelled fixtures (deterministic in both modes)."""
    gold = yaml.safe_load((GOLD / "injection.yaml").read_text())
    postings = _fixture_postings(svc)
    flagged = {pid for pid, p in postings.items() if scan(f"{p.title}\n{p.description}").flagged}
    truth = set(gold["flagged"])
    p, r, _ = _prf(len(flagged & truth), len(flagged - truth), len(truth - flagged))
    details = [{"id": i, "expected": i in truth, "flagged": i in flagged} for i in sorted(postings)]
    return SuiteResult("injection", mode, {"precision": p, "recall": r}, {}, details)


def verifier_suite(svc: Services, mode: Mode) -> SuiteResult:
    """Entailment labels on hand-written claims, including seeded fabrications."""
    cases = yaml.safe_load((GOLD / "seeded_claims.yaml").read_text())["cases"]
    llm = svc.models.get_model("cheap")
    correct = fab_caught = fab_total = 0
    details = []
    for c in cases:
        ev = [
            EvidenceItem(id=f"{c['id']}-e{i}", kind="experience", text=t, source_ref="eval")
            for i, t in enumerate(c["evidence"])
        ]
        claim = Claim(text=c["claim"], evidence_ids=[e.id for e in ev])
        out = llm.structured(
            task="verify_claim",
            schema=Entailment,
            system=VERIFY_SYSTEM,
            prompt=verify_prompt(claim, ev),
            payload={"claim": c["claim"], "evidence": [e.model_dump() for e in ev]},
            run_id=f"eval-verifier-{mode}",
        )
        correct += out.label == c["expected"]
        if c.get("fabricated"):
            fab_total += 1
            fab_caught += out.label == "unsupported"
        details.append(
            {"id": c["id"], "expected": c["expected"], "got": out.label, "reason": out.reason}
        )
    metrics = {
        "label_accuracy": correct / len(cases),
        "fabricated_recall": fab_caught / max(fab_total, 1),
    }
    return SuiteResult("verifier", mode, metrics, {}, details)


def ranking_auc(pos: list[float], neg: list[float]) -> float:
    """Probability that a random positive outscores a random negative (ties count half)."""
    if not pos or not neg:
        return 1.0
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _match_metrics(
    scores: dict[str, float], shortlisted: set[str], labels: dict[str, str]
) -> dict[str, float]:
    approve = {j for j, lab in labels.items() if lab == "approve" and j in scores}
    reject = {j for j, lab in labels.items() if lab == "reject" and j in scores}
    hits = shortlisted & approve
    return {
        "precision_at_shortlist": len(hits) / len(shortlisted) if shortlisted else 0.0,
        "recall_at_shortlist": len(hits) / len(approve) if approve else 0.0,
        "ranking_auc": ranking_auc([scores[j] for j in approve], [scores[j] for j in reject]),
    }


def match_suite(svc: Services, mode: Mode) -> SuiteResult:
    """Run nodes 1-5 on the fixtures and compare shortlist/ranking with the triage labels."""
    labels = {
        k: v["label"] for k, v in yaml.safe_load((GOLD / "triage_labels.yaml").read_text()).items()
    }
    out = build_jobs_graph().compile().invoke({"run_id": f"eval-match-{mode}"}, context=svc)
    scores = {m.job_id: m.score for m in out["matches"]}
    short = set(out["shortlist"])
    details = [
        {
            "id": m.job_id,
            "score": m.score,
            "shortlisted": m.job_id in short,
            "label": labels.get(m.job_id),
            "dealbreakers": m.dealbreakers,
        }
        for m in out["matches"]
    ]
    return SuiteResult("match", mode, _match_metrics(scores, short, labels), {}, details)


def match_suite_from_labels(
    cfg: AppConfig, repo: Repository, labels_path: Path, store: Any
) -> SuiteResult:
    """Offline: re-score YOUR stored postings with the current criteria against labels exported
    by `eval export-labels`. No LLM calls."""
    raw: dict[str, dict[str, Any]] = yaml.safe_load(labels_path.read_text()) or {}
    profile = repo.latest_profile()
    if profile is None:
        raise ValueError("no cached profile: run `make profile` first")
    svc = build_services(cfg, repo)
    docs = [(e.id, f"{e.text} {' '.join(e.skills)}") for e in profile.evidence]
    sctx = ScoringContext(cfg, profile, HybridIndex(docs, svc.embedder), svc.skills)
    weights = preferences.load(store)
    scores: dict[str, float] = {}
    notes = []
    for job_id in raw:
        job = repo.cached_analysis_by_posting(job_id)
        if job is None:
            notes.append(f"{job_id}: no stored analysis, skipped")
            continue
        scores[job_id] = score_job(job, sctx, preferences.adjustment(weights, job)).score
    ranked = sorted(scores, key=lambda j: -scores[j])
    short = set(ranked[: cfg.criteria.top_n]) & {
        j for j in scores if scores[j] >= cfg.criteria.threshold
    }
    labels = {k: v["label"] for k, v in raw.items()}
    return SuiteResult("match", "labels", _match_metrics(scores, short, labels), {}, notes=notes)


def run_suite(name: str, base: Settings, mode: Mode) -> SuiteResult:
    """Run one suite in an isolated temp workspace and attach its thresholds."""
    runners = {
        "match": match_suite,
        "extraction": extraction_suite,
        "verifier": verifier_suite,
        "injection": injection_suite,
    }
    with tempfile.TemporaryDirectory(prefix="careergraph-eval-") as tmp:
        result = runners[name](eval_services(base, mode, Path(tmp)), mode)
    result.thresholds = load_thresholds().get(name, {}) if mode == "fake" else {}
    if mode == "live":
        result.notes.append("Live mode is not gated; compare against previous live reports.")
    return result
