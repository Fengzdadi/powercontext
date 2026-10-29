"""Unit tests for embedding query-instruction handling (no model load)."""
from types import SimpleNamespace

import examradar.embedding as emb


def _make_model(instruction: str) -> emb.EmbeddingModel:
    model = emb.EmbeddingModel.__new__(emb.EmbeddingModel)
    model._settings = SimpleNamespace(
        embedding_query_instruction=instruction,
        embedding_provider="local",
    )
    return model


def test_instruction_applied_when_configured(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        emb.EmbeddingModel, "embed",
        lambda self, texts: captured.update(texts=texts) or [[0.0]],
    )
    model = _make_model("为这个句子生成表示以用于检索相关文章：")
    model.embed_one("脏页表", is_query=True)
    assert captured["texts"] == ["为这个句子生成表示以用于检索相关文章：脏页表"]
    model.embed_one("脏页表")
    assert captured["texts"] == ["脏页表"]


def test_no_instruction_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        emb.EmbeddingModel, "embed",
        lambda self, texts: captured.update(texts=texts) or [[0.0]],
    )
    model = _make_model("")
    model.embed_one("脏页表", is_query=True)
    assert captured["texts"] == ["脏页表"]
