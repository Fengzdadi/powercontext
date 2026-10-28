"""Local text embeddings (bge-small-zh via fastembed, baked into the image) for seekdb vector search."""

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("court.embedding")


class Embedder:
    def __init__(self) -> None:
        self.model_name = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        self.dim = int(os.environ.get("EMBEDDING_DIM", "512"))
        self.cache_dir = os.environ.get("EMBEDDING_CACHE_DIR", "/models")
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None

    def load(self) -> None:
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
            probe = next(iter(self._model.embed(["喵"])))
            if len(probe) != self.dim:
                raise ValueError(f"model returned {len(probe)} dims, expected {self.dim}")
            log.info("embedding model %s ready (%d dims)", self.model_name, self.dim)
        except Exception as exc:  # noqa: BLE001 - search degrades to full-text only
            self._model = None
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("embedding model unavailable, vector search disabled: %s", self.error)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def embed_documents(self, texts: list[str]) -> list[list[float]] | None:
        if not self.ready or not texts:
            return None
        with self._lock:
            return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float] | None:
        if not self.ready or not text:
            return None
        with self._lock:
            return next(iter(self._model.query_embed([text]))).tolist()
