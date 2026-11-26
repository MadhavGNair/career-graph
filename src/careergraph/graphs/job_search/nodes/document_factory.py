"""document_factory (runs once per approved job, in parallel, via Send)

Purpose:      Run the document_factory subgraph (draft <-> verify loop) for one job.
Reads:        branch payload {run_id, job, evidence, evidence_pool, research, draft, critique, mode}
Writes:       drafts[job_id]  (merged by the reducer)
Uses LLM?:    via the subgraph (strong for drafting, cheap for verification)
Side effects: none (the subgraph inherits the parent's checkpointer)
Config keys:  MAX_REVISIONS
"""

from __future__ import annotations

from typing import Any

from careergraph.graphs.job_search.context import Ctx
from careergraph.graphs.job_search.subgraphs.document_factory import DOCUMENT_FACTORY
from careergraph.graphs.job_search.subgraphs.state import DocState


def document_factory(branch: DocState, runtime: Ctx) -> dict[str, Any]:
    """Draft and verify one job's documents."""
    result = DOCUMENT_FACTORY.invoke(branch, context=runtime.context)
    return {"drafts": {branch["job"].posting.id: result["draft"]}}
