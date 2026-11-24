"""Hybrid evidence index: BM25 (lexical) + cosine (semantic), fused by reciprocal rank."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from careergraph.retrieval.embeddings import Embedder

_TOKEN = re.compile(r"[a-z0-9+#]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "the",
        "to",
        "we",
        "with",
        "you",
        "your",
        "will",
        "this",
        "that",
        "who",
        "what",
    ]
)
RRF_K = 60


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stopwords."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class Hit:
    """One retrieval result."""

    doc_id: str
    rrf: float
    cosine: float
    bm25: float


class HybridIndex:
    """In-process index over (id, text) pairs. Small by design: one user's evidence."""

    def __init__(self, docs: list[tuple[str, str]], embedder: Embedder) -> None:
        self.ids = [d for d, _ in docs]
        self.texts = [t for _, t in docs]
        self._embedder = embedder
        tokens = [tokenize(t) or ["_"] for t in self.texts]
        self._bm25 = BM25Okapi(tokens) if docs else None
        self._vecs = embedder.embed(self.texts) if docs else np.zeros((0, 1), dtype=np.float32)

    def search(self, query: str, k: int = 8) -> list[Hit]:
        """Return the top-k documents by RRF over BM25 and cosine rankings."""
        if not self.ids or self._bm25 is None:
            return []
        bm25 = np.asarray(self._bm25.get_scores(tokenize(query) or ["_"]), dtype=np.float64)
        cos = self._vecs @ self._embedder.embed([query])[0]
        rrf = np.zeros(len(self.ids))
        for scores in (bm25, cos):
            order = np.argsort(-scores, kind="stable")
            ranks = np.empty(len(order), dtype=np.int64)
            ranks[order] = np.arange(len(order))
            rrf += 1.0 / (RRF_K + ranks + 1)
        top = np.argsort(-rrf, kind="stable")[:k]
        return [Hit(self.ids[i], float(rrf[i]), float(cos[i]), float(bm25[i])) for i in top]

    def semantic_similarity(self, query: str, top: int = 3) -> float:
        """Mean cosine of the top documents, clipped to [0, 1] (backend-relative scale)."""
        if not self.ids:
            return 0.0
        cos = np.sort(self._vecs @ self._embedder.embed([query])[0])[::-1][:top]
        return float(np.clip(cos.mean(), 0.0, 1.0))
