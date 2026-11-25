"""Learn preferences from shortlist decisions and turn them into score adjustments.

Deterministic, no LLM, no free-text interpretation. Each job is described by features
(seniority, remote type, city, company, top must-have skills, salary band). Reason tags say
which features caused a rejection; approvals reinforce all of a job's features.

Store layout: namespace ("preferences", "default"); key = feature; value =
{"weight": float, "approvals": int, "rejections": int}.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langgraph.store.base import BaseStore

from careergraph.domain.models import AnalyzedJob, ReasonTag, ShortlistDecision

NAMESPACE = ("preferences", "default")
POINTS_PER_UNIT = 2.5
APPROVE_STEP = 0.5
REJECT_STEP = 1.0


def job_features(job: AnalyzedJob) -> dict[str, list[str]]:
    """Features grouped by the reason tag that can explain them."""
    a, p = job.analysis, job.posting
    city = p.location.split(",")[0].split("(")[0].strip().lower() or "unknown"
    band = "unknown"
    if a.salary and a.salary.max:
        band = f"{a.salary.currency}:<{(a.salary.max // 20000 + 1) * 20}k"
    seniority = [f"seniority:{a.seniority}"]
    return {
        ReasonTag.TOO_JUNIOR: seniority,
        ReasonTag.TOO_SENIOR: seniority,
        ReasonTag.WRONG_LOCATION: [f"location:{city}", f"remote:{a.remote}"],
        ReasonTag.NOT_MY_DOMAIN: [f"skill:{s}" for s in a.must_have[:3]],
        ReasonTag.COMPANY: [f"company:{p.company.lower()}"],
        ReasonTag.SALARY: [f"salary:{band}"],
    }


def all_features(job: AnalyzedJob) -> set[str]:
    """Every feature of a job."""
    return {f for feats in job_features(job).values() for f in feats}


def _bump(store: BaseStore, feature: str, delta: float, field: str) -> None:
    item = store.get(NAMESPACE, feature)
    value: dict[str, Any] = (
        dict(item.value) if item else {"weight": 0.0, "approvals": 0, "rejections": 0}
    )
    value["weight"] = round(float(value["weight"]) + delta, 4)
    value[field] = int(value[field]) + 1
    store.put(NAMESPACE, feature, value)


def learn(
    store: BaseStore, decisions: Iterable[ShortlistDecision], jobs: dict[str, AnalyzedJob]
) -> int:
    """Write preference updates for decisions; returns how many features changed."""
    changed = 0
    for d in decisions:
        job = jobs.get(d.job_id)
        if job is None:
            continue
        if d.decision == "approve":
            for f in sorted(all_features(job)):
                _bump(store, f, APPROVE_STEP, "approvals")
                changed += 1
        elif d.decision == "reject":
            feats = job_features(job)
            for tag in d.reason_tags:
                for f in feats.get(tag, []):
                    _bump(store, f, -REJECT_STEP, "rejections")
                    changed += 1
    return changed


def load(store: BaseStore | None) -> dict[str, float]:
    """All learned feature weights."""
    if store is None:
        return {}
    return {
        it.key: float(it.value.get("weight", 0.0)) for it in store.search(NAMESPACE, limit=1000)
    }


def adjustment(weights: dict[str, float], job: AnalyzedJob) -> float:
    """Unclipped points for a job (scoring clips to criteria.preference.max_adjustment)."""
    return POINTS_PER_UNIT * sum(weights.get(f, 0.0) for f in all_features(job))
