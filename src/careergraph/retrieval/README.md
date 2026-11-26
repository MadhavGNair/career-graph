# retrieval/

## Purpose
Find the evidence most relevant to a posting, in-process: BM25 (lexical) plus embeddings
(semantic), fused with reciprocal rank fusion (RRF). No vector database.

## How it works
```mermaid
flowchart LR
  Q[posting text / skill] --> B[BM25Okapi]
  Q --> E[embed + cosine]
  B --> R[RRF: sum 1/(60+rank)]
  E --> R --> Top[top-k evidence ids]
  E --> S[semantic_similarity: mean top-3 cosine]
```
- `HybridIndex.search` ranks evidence for per-skill evidence ids and for draft selection.
- `HybridIndex.semantic_similarity` feeds the `semantic` criterion in `match_jobs`.
- Embedders: `HashingEmbedder` (deterministic feature hashing, no download, used in demo, tests
  and CI) and `FastEmbedEmbedder` (`BAAI/bge-small-en-v1.5` by default, ONNX on CPU) with a
  SQLite cache keyed by `sha256(model + text)` under `CACHE_DIR`.

## LangGraph concepts used and why
Used inside `match_jobs` and `select_evidence`; the index is rebuilt per run from the profile
in state (cheap) rather than stored in the checkpoint.

## Key files
`embeddings.py` (backends + cache), `index.py` (BM25 + cosine + RRF).

## Configuration
`EMBEDDING_BACKEND` (`auto` = hashing in demo, fastembed in live), `EMBEDDING_MODEL`, `CACHE_DIR`.

## How to test
`uv run pytest tests/test_retrieval.py`.

## Design decisions and trade-offs
One user's evidence is tens to hundreds of items, so a brute-force matrix product is instant
and a vector DB would add infrastructure for nothing (see ADR 0004). RRF avoids calibrating
BM25 against cosine scores. The semantic criterion uses raw cosine, whose scale depends on the
backend: compare scores only within one backend.

## Extending and gotchas
- fastembed downloads the model on first use (network). Demo/CI never use it.
- Hashing-embedder similarity is a plumbing signal, not semantic quality.
