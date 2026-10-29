from __future__ import annotations

import os
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

    powercontext_url: str = "http://127.0.0.1:18801"

    app_host: str = "127.0.0.1"
    app_port: int = 18800
    cors_origins: str = "http://localhost:18800"

    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_base_url: Optional[str] = None
    embedding_api_key: Optional[str] = None

    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None

    coverage_t_covered: float = 0.55
    coverage_t_thin: float = 0.20
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
