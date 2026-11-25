"""Assemble a ProfileSnapshot from extracted and pinned evidence (deterministic)."""

from __future__ import annotations

import re

from careergraph.domain.models import EvidenceDraft, EvidenceItem, ProfileSnapshot
from careergraph.skills.normalize import SkillNormalizer


def _key(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def build_snapshot(
    drafts: list[EvidenceDraft],
    pinned: list[EvidenceItem],
    skills: SkillNormalizer,
    hashes: dict[str, str],
) -> ProfileSnapshot:
    """Merge pinned items (kept verbatim, ids preserved) with extracted ones (ids ev-001...).

    Skills are canonicalised; duplicate texts are dropped (pinned wins).
    """
    evidence: list[EvidenceItem] = []
    seen: set[str] = set()
    for p in pinned:
        evidence.append(p.model_copy(update={"skills": skills.normalize_all(p.skills)}))
        seen.add(_key(p.text))
    n = 0
    for d in drafts:
        k = _key(d.text)
        if not k or k in seen:
            continue
        seen.add(k)
        n += 1
        evidence.append(
            EvidenceItem(
                id=f"ev-{n:03d}",
                kind=d.kind,
                text=d.text.strip(),
                skills=skills.normalize_all(d.skills),
                source_ref=d.source_ref,
                dates=d.dates,
            )
        )
    index: dict[str, list[str]] = {}
    for e in evidence:
        for s in e.skills:
            index.setdefault(s, []).append(e.id)
    return ProfileSnapshot(evidence=evidence, skills=dict(sorted(index.items())), hashes=hashes)
