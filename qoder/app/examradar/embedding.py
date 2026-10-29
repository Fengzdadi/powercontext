"""Embedding generation using fastembed (local) or OpenAI-compatible API."""
from __future__ import annotations

import json
from typing import Optional

import httpx

from .config import get_settings


class EmbeddingModel:
    def __init__(self):
        self._settings = get_settings()
        self._local_model = None

    def _get_local_model(self):
        if self._local_model is None:
            from fastembed import TextEmbedding
            self._local_model = TextEmbedding(self._settings.embedding_model)
        return self._local_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._settings.embedding_provider == "openai":
            return self._embed_openai(texts)
        return self._embed_local(texts)

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        model = self._get_local_model()
        embeddings = list(model.embed(texts))
        return [e.tolist() for e in embeddings]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        s = self._settings
        if not s.embedding_base_url or not s.embedding_api_key:
            raise ValueError("OpenAI embedding requires EMBEDDING_BASE_URL and EMBEDDING_API_KEY")
        resp = httpx.post(
            f"{s.embedding_base_url}/embeddings",
            headers={"Authorization": f"Bearer {s.embedding_api_key}"},
            json={"model": s.embedding_model, "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


_model_instance: Optional[EmbeddingModel] = None


def get_embedding_model() -> EmbeddingModel:
    global _model_instance
    if _model_instance is None:
        _model_instance = EmbeddingModel()
    return _model_instance
