"""Deterministic, explainable job scoring against config/criteria.yaml.

score = 100 * sum(weight_i * criterion_i)  (weights normalised, criteria in [0, 1])
        + learned preference adjustment (clipped to +-max_adjustment), clipped to [0, 100].
Dealbreakers remove a job from the shortlist regardless of score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from careergraph.config import AppConfig
from careergraph.domain.models import (
    AnalyzedJob,
    CriterionScore,
    MatchResult,
    ProfileSnapshot,
    SkillMatch,
)
from careergraph.retrieval.index import HybridIndex
from careergraph.skills.normalize import SkillNormalizer

LEVELS = ["intern", "junior", "mid", "senior", "staff", "principal"]
LEVEL_ALIAS = {"lead": "staff"}
LANG_LEVEL = {"native": 1.0, "fluent": 1.0, "professional": 1.0, "intermediate": 0.5, "basic": 0.25}
_TOKEN = re.compile(r"[a-z0-9+#]+")
NEUTRAL = 0.5


@dataclass(frozen=True)
class ScoringContext:
    """Everything that is the same for every job in one run."""

    cfg: AppConfig
    profile: ProfileSnapshot
    index: HybridIndex
    skills: SkillNormalizer


def skill_matches(job: AnalyzedJob, ctx: ScoringContext) -> list[SkillMatch]:
    """Classify every required skill as matched, partial (related skill) or missing."""
    have = ctx.profile.skills
    out: list[SkillMatch] = []
    groups: list[tuple[Literal["must", "nice"], list[str]]] = [
        ("must", job.analysis.must_have),
        ("nice", job.analysis.nice_to_have),
    ]
    for requirement, names in groups:
        for skill in names:
            if skill in have:
                out.append(
                    SkillMatch(
                        skill=skill,
                        requirement=requirement,
                        status="matched",
                        evidence_ids=have[skill][:3],
                    )
                )
                continue
            related = sorted(r for r in ctx.skills.related(skill) if r in have)
            if related:
                out.append(
                    SkillMatch(
                        skill=skill,
                        requirement=requirement,
                        status="partial",
                        via=related[0],
                        evidence_ids=have[related[0]][:3],
                    )
                )
            else:
                out.append(SkillMatch(skill=skill, requirement=requirement, status="missing"))
    return out


def coverage(matches: list[SkillMatch], requirement: str, partial_credit: float) -> float:
    """Share of required skills covered; partial matches count partial_credit."""
    rel = [m for m in matches if m.requirement == requirement]
    if not rel:
        return NEUTRAL
    got = sum(
        1.0 if m.status == "matched" else partial_credit if m.status == "partial" else 0.0
        for m in rel
    )
    return got / len(rel)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def title_fit(title: str, cfg: AppConfig) -> float:
    """Half: best overlap with a search.yaml include keyword; half: overlap with your headline."""
    t = _tokens(title)

    def frac(target: str) -> float:
        tt = _tokens(target)
        return len(t & tt) / len(tt) if tt else 0.0

    includes = cfg.search.titles.include
    best = max((frac(x) for x in includes), default=1.0)
    head = frac(cfg.profile.identity.headline) if cfg.profile.identity.headline else best
    return 0.5 * best + 0.5 * head


def seniority_fit(level: str, targets: list[str]) -> float:
    """1 if targeted, 0.5 if one level away or unknown, else 0."""
    if level == "unknown":
        return NEUTRAL
    level = LEVEL_ALIAS.get(level, level)
    wanted = {LEVEL_ALIAS.get(x, x) for x in targets}
    if level in wanted:
        return 1.0
    if level not in LEVELS:
        return NEUTRAL
    i = LEVELS.index(level)
    near = {LEVELS[j] for j in (i - 1, i + 1) if 0 <= j < len(LEVELS)}
    return 0.5 if near & wanted else 0.0


def location_fit(job: AnalyzedJob, cfg: AppConfig) -> float:
    """Remote is best (unless excluded); hybrid/on-site in your home city next; elsewhere less."""
    remote = job.analysis.remote if job.analysis.remote != "unknown" else job.posting.remote
    pref = cfg.search.locations.remote
    if remote == "remote":
        return 0.0 if pref == "excluded" else 1.0
    home = cfg.profile.identity.location.split(",")[0].strip().lower()
    in_home = bool(home) and home in job.posting.location.lower()
    if remote == "unknown":
        return 0.8 if in_home else NEUTRAL
    if in_home:
        return 1.0 if remote == "hybrid" or pref != "preferred" else 0.8
    return 0.6 if remote == "hybrid" else 0.4


def language_fit(job: AnalyzedJob, cfg: AppConfig) -> tuple[float, list[str]]:
    """Lowest proficiency across required languages (English assumed ok if you list it)."""
    spoken = {lang.code.lower(): LANG_LEVEL[lang.level] for lang in cfg.profile.identity.languages}
    required = [x for x in job.analysis.languages if x != "en" or "en" not in spoken]
    if not required:
        return 1.0, []
    levels = {x: spoken.get(x, 0.0) for x in required}
    return min(levels.values()), [x for x, v in levels.items() if v == 0.0]


def salary_fit(job: AnalyzedJob, cfg: AppConfig) -> tuple[float, bool]:
    """(score, below_floor). Unknown salary or currency mismatch is neutral, never penalised."""
    floor = cfg.criteria.salary_floor
    sal = job.analysis.salary
    if (
        floor.amount is None
        or sal is None
        or sal.max is None
        or (sal.currency or "") != floor.currency
    ):
        return NEUTRAL, False
    return (1.0, False) if sal.max >= floor.amount else (0.0, True)


def dealbreakers(
    job: AnalyzedJob, ctx: ScoringContext, missing_langs: list[str], below_floor: bool
) -> list[str]:
    """Hard filters from criteria.yaml."""
    db = ctx.cfg.criteria.dealbreakers
    hits: list[str] = []
    if job.posting.company.lower() in {c.lower() for c in db.excluded_companies}:
        hits.append(f"excluded company: {job.posting.company}")
    text = f"{job.posting.title}\n{job.posting.description}".lower()
    for kw in db.excluded_keywords:
        if re.search(rf"(?<!\w){re.escape(kw.lower())}(?!\w)", text):
            hits.append(f"excluded keyword: {kw}")
    if db.require_language_match and missing_langs:
        hits.append(f"requires language you do not speak: {', '.join(missing_langs)}")
    if db.enforce_salary_floor and below_floor:
        hits.append("salary below your floor")
    return hits


def score_job(job: AnalyzedJob, ctx: ScoringContext, preference_points: float) -> MatchResult:
    """Score one job with a full breakdown."""
    crit = ctx.cfg.criteria
    w = crit.weights.normalised()
    matches = skill_matches(job, ctx)
    query = " ".join(
        [
            job.posting.title,
            job.analysis.summary,
            *job.analysis.must_have,
            *job.analysis.nice_to_have,
        ]
    )
    lang_score, missing_langs = language_fit(job, ctx.cfg)
    sal_score, below = salary_fit(job, ctx.cfg)
    parts = {
        "must_have": (
            coverage(matches, "must", crit.related_skill_credit),
            "required skills covered",
        ),
        "nice_to_have": (
            coverage(matches, "nice", crit.related_skill_credit),
            "bonus skills covered",
        ),
        "semantic": (
            ctx.index.semantic_similarity(query),
            "evidence similarity (hybrid retrieval)",
        ),
        "title": (title_fit(job.posting.title, ctx.cfg), "title vs targets and headline"),
        "seniority": (
            seniority_fit(job.analysis.seniority, list(crit.target_seniority)),
            job.analysis.seniority,
        ),
        "location": (location_fit(job, ctx.cfg), f"{job.posting.location} / {job.analysis.remote}"),
        "language": (lang_score, ",".join(job.analysis.languages) or "none stated"),
        "salary": (sal_score, "below floor" if below else "ok or unknown"),
    }
    breakdown = [
        CriterionScore(
            name=k,
            weight=round(w[k], 4),
            score=round(s, 4),
            points=round(100 * w[k] * s, 2),
            detail=d,
        )
        for k, (s, d) in parts.items()
    ]
    cap = crit.preference.max_adjustment if crit.preference.enabled else 0.0
    adj = max(-cap, min(cap, preference_points))
    total = max(0.0, min(100.0, sum(c.points for c in breakdown) + adj))
    return MatchResult(
        job_id=job.posting.id,
        score=round(total, 1),
        breakdown=breakdown,
        skills=matches,
        dealbreakers=dealbreakers(job, ctx, missing_langs, below),
        preference_adjustment=round(adj, 2),
    )


def shortlist(results: list[MatchResult], threshold: float, top_n: int) -> list[str]:
    """Rank by score (ties by id) and keep dealbreaker-free jobs above the threshold."""
    ranked = sorted(results, key=lambda r: (-r.score, r.job_id))
    return [r.job_id for r in ranked if not r.dealbreakers and r.score >= threshold][:top_n]


def default_rationale(r: MatchResult) -> str:
    """Deterministic rationale used when ENABLE_MATCH_RATIONALE=false."""
    matched = [m.skill for m in r.skills_with("matched")][:3]
    missing = [m.skill for m in r.skills_with("missing") if m.requirement == "must"][:3]
    text = f"Score {r.score:.0f}"
    text += f"; evidence for {', '.join(matched)}" if matched else ""
    text += f"; missing {', '.join(missing)}" if missing else ""
    return text + "."
