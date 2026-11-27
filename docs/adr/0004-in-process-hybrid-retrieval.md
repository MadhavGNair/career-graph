# ADR 0004: In-process hybrid retrieval instead of pgvector

Status: accepted (2026-11-22)

## Context
Retrieval is over one person's evidence: tens to a few hundred short items.

## Decision
BM25 (`rank_bm25`) + local embeddings (fastembed, small model) fused with reciprocal rank
fusion, computed in-process; embeddings cached on disk by text hash. A deterministic hashing
embedder serves demo, tests and CI (no download).

## Consequences
No vector database to run or pay for. Index rebuilds per run are instant at this size. If
evidence ever reaches tens of thousands of items, pgvector (already Postgres-compatible) is the
upgrade path.
