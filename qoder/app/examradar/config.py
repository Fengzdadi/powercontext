from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Optional[str]:
    """Walk up from this file to find .env (lives at repo root = qoder/.env)."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    seekdb_host: str = "127.0.0.1"
    seekdb_port: int = 10800
    seekdb_user: str = "root"
    seekdb_password: str = "change-me"
    seekdb_database: str = "examradar"
    seekdb_test_database: str = "examradar_test"

    powercontext_url: str = "http://127.0.0.1:18801"
    powercontext_timeout_seconds: float = 8.0

    # 学习会话：无事件超过该分钟数视为已结束（时长按最后一个事件计）
    session_idle_minutes: int = 30

    # Ollama：同一模型每次调用使用相同的 num_ctx，避免反复重载模型
    llm_num_ctx: int = 8192
    llm_max_context_bytes: int = 6000
    pc_context_max_bytes: int = 2000

    app_host: str = "127.0.0.1"
    app_port: int = 18800
    cors_origins: str = "http://localhost:18800"

    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    # BGE retrieval instruction prefixed to queries, e.g.
    # "为这个句子生成表示以用于检索相关文章：". Empty = disabled. Measured on
    # the acceptance queries (DEVLOG session 03): the instruction did not
    # improve semantic ranking for short Chinese term queries and flipped
    # near-tied candidates, so it is off by default.
    embedding_query_instruction: str = ""
    embedding_base_url: Optional[str] = None
    embedding_api_key: Optional[str] = None

    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None

    # Coverage judgment (see DEVLOG session 05). Evidence is "term appears in
    # the corpus"; semantic scores only rank evidence, never decide coverage.
    # covered requires: >= this fraction of the topic's terms found ...
    coverage_term_ratio_covered: float = 0.5
    # ... and at least this many characters of supporting body text
    coverage_support_chars: int = 280
    # chunks whose body (content minus heading lines) is shorter than this
    # never count as evidence (title-only pages / one-line notes)
    coverage_min_body_chars: int = 50

    # Usage stats: estimated study time from events (real sessions arrive in M3)
    usage_session_gap_minutes: int = 30
    usage_minutes_per_event: float = 1.0

    leitner_intervals: str = "1,2,4,7,14"

    @property
    def leitner_intervals_list(self) -> list[int]:
        return [int(x) for x in self.leitner_intervals.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
