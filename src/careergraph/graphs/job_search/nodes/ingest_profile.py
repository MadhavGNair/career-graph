"""ingest_profile

Purpose:      Read the user's documents and GitHub repos into ProfileDocuments and decide
              whether the cached extraction is still valid.
Reads:        force_profile
Writes:       documents, pinned, profile_key, profile_cached, profile (when cached)
Uses LLM?:    deterministic
Side effects: HTTP to api.github.com via SafeFetcher (fixtures in demo); reads profile files
Config keys:  profile.yaml documents.{dir,include,evidence_file}, github.{username,max_repos,
              readme_max_chars}; GITHUB_TOKEN
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.state import JobSearchState
from careergraph.security.fetcher import FetchError
from careergraph.sources.documents import load_documents, load_pinned_evidence

log = logging.getLogger(__name__)


def ingest_profile(state: JobSearchState, runtime: Ctx) -> dict[str, Any]:
    """Load documents, GitHub repos and pinned evidence; look up the extraction cache."""
    ctx = runtime.context
    spec = ctx.cfg.profile
    folder = ctx.settings.resolve(Path(spec.documents.dir))
    docs = load_documents(folder, spec.documents.include, skip={spec.documents.evidence_file})
    if spec.github.username:
        try:
            docs += ctx.github.fetch_profile(
                spec.github.username, spec.github.max_repos, spec.github.readme_max_chars
            )
        except FetchError as exc:
            log.warning("github ingest failed; continuing without it", extra={"error": str(exc)})
    pinned = load_pinned_evidence(folder / spec.documents.evidence_file)
    fingerprint = json.dumps(
        {
            "docs": sorted((d.source_id, d.content_hash) for d in docs),
            "pinned": [p.model_dump(mode="json") for p in pinned],
            "skills": ctx.cfg.skills.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    key = hashlib.sha256(fingerprint.encode()).hexdigest()
    cached = None if state.get("force_profile") else ctx.repo.get_profile(key)
    update: dict[str, Any] = {
        "documents": docs,
        "pinned": pinned,
        "profile_key": key,
        "profile_cached": cached is not None,
    }
    if cached is not None:
        update["profile"] = cached
    log.info("profile ingested", extra={"documents": len(docs), "cached": cached is not None})
    return update
