"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from ..seekdb import check_connection
from ..pc_client import check_powercontext
from ..embedding import get_embedding_model
from ..config import get_settings

router = APIRouter()


@router.get("/api/health")
def health():
    s = get_settings()

    seekdb_ok = check_connection()

    try:
        model = get_embedding_model()
        vec = model.embed_one("测试")
        emb_ok = len(vec) == s.embedding_dim
        emb_info = f"{s.embedding_model} ({s.embedding_dim}d)"
    except Exception as e:
        emb_ok = False
        emb_info = str(e)

    pc_ok, pc_msg = check_powercontext()

    return {
        "seekdb": {"ok": seekdb_ok},
        "embedding": {"ok": emb_ok, "model": emb_info},
        "powercontext": {"ok": pc_ok, "detail": pc_msg},
    }
