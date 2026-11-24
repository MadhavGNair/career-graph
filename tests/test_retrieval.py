"""Hybrid retrieval with the deterministic hashing embedder."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from careergraph.retrieval.embeddings import EmbeddingCache, HashingEmbedder
from careergraph.retrieval.index import HybridIndex, tokenize

DOCS = [
    ("ev-1", "Designed an ML platform on Kubernetes serving 35 models"),
    ("ev-2", "Built a recommender system with PyTorch for retail"),
    ("ev-3", "Developed demand forecasting with time series and Spark"),
]


def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    e = HashingEmbedder()
    a, b = e.embed(["kubernetes platform"]), e.embed(["kubernetes platform"])
    assert np.allclose(a, b)
    assert abs(float(np.linalg.norm(a[0])) - 1.0) < 1e-5


def test_search_ranks_relevant_doc_first() -> None:
    idx = HybridIndex(DOCS, HashingEmbedder())
    assert idx.search("kubernetes ml platform", k=1)[0].doc_id == "ev-1"
    assert idx.search("recommender pytorch", k=1)[0].doc_id == "ev-2"
    assert idx.semantic_similarity("forecasting time series") > idx.semantic_similarity(
        "baking bread"
    )


def test_empty_index() -> None:
    idx = HybridIndex([], HashingEmbedder())
    assert idx.search("x") == [] and idx.semantic_similarity("x") == 0.0


def test_tokenize_drops_stopwords() -> None:
    assert tokenize("The C++ and Python of it") == ["c++", "python"]


def test_embedding_cache_roundtrip(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "e.sqlite")
    k = EmbeddingCache.key("m", "hello")
    cache.put_many({k: np.ones(4, dtype=np.float32)})
    assert np.allclose(cache.get_many([k, "missing"])[k], np.ones(4))
