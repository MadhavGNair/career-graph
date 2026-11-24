"""Embedding backends: deterministic hashing (tests/CI/demo) and fastembed (live), with a
SQLite disk cache keyed by model + text hash."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

Vectors = NDArray[np.float32]
_WORD = re.compile(r"[a-z0-9+#]+")


class Embedder(Protocol):
    """Turns texts into L2-normalised vectors."""

    name: str

    def embed(self, texts: list[str]) -> Vectors:
        """Embed texts into a (n, dim) float32 matrix with unit rows."""
        ...


def _normalise(m: Vectors) -> Vectors:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class HashingEmbedder:
    """Feature-hashing of words and character trigrams. Deterministic, no download.

    Quality is far below a real model; it exists so tests, CI and the demo never need the
    network. Semantic-match numbers from it are plumbing checks, not model quality.
    """

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(text.lower())
        grams = [w[i : i + 3] for w in words if len(w) > 3 for i in range(len(w) - 2)]
        return words + [f"#{g}" for g in grams]

    def embed(self, texts: list[str]) -> Vectors:
        """Embed texts by hashing features into signed buckets."""
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                weight = 1.0 if not feat.startswith("#") else 0.5
                out[row, idx] += sign * weight
        return _normalise(out)


class EmbeddingCache:
    """Thread-safe SQLite cache: sha256(model + text) -> float32 vector bytes."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")
        self._lock = threading.Lock()

    @staticmethod
    def key(model: str, text: str) -> str:
        """Cache key for a model/text pair."""
        return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, NDArray[np.float32]]:
        """Return cached vectors for the keys that exist."""
        if not keys:
            return {}
        with self._lock:
            marks = ",".join("?" * len(keys))
            rows = self._conn.execute(f"SELECT k, v FROM emb WHERE k IN ({marks})", keys)  # noqa: S608
            return {k: np.frombuffer(v, dtype=np.float32) for k, v in rows}

    def put_many(self, items: dict[str, NDArray[np.float32]]) -> None:
        """Store vectors."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO emb VALUES (?, ?)",
                [(k, v.astype(np.float32).tobytes()) for k, v in items.items()],
            )
            self._conn.commit()


class FastEmbedEmbedder:
    """fastembed (ONNX, CPU) with a disk cache. The model downloads once into cache_dir."""

    def __init__(self, model_name: str, cache_dir: Path) -> None:
        self.name = model_name
        self._cache_dir = cache_dir
        self._cache = EmbeddingCache(cache_dir / "embeddings.sqlite")
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # heavy import, only in live mode

            self._model = TextEmbedding(self.name, cache_dir=str(self._cache_dir / "fastembed"))
        return self._model

    def embed(self, texts: list[str]) -> Vectors:
        """Embed texts, computing only cache misses."""
        keys = [EmbeddingCache.key(self.name, t) for t in texts]
        cached = self._cache.get_many(keys)
        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in cached]
        if missing:
            vecs = list(self._load().embed([t for _, t in missing]))
            new = {
                k: np.asarray(v, dtype=np.float32) for (k, _), v in zip(missing, vecs, strict=True)
            }
            self._cache.put_many(new)
            cached.update(new)
        return _normalise(np.stack([cached[k] for k in keys]))


def make_embedder(backend: str, model_name: str, cache_dir: Path) -> Embedder:
    """Build the configured embedder (`hashing` or `fastembed`)."""
    if backend == "fastembed":
        return FastEmbedEmbedder(model_name, cache_dir)
    return HashingEmbedder()
