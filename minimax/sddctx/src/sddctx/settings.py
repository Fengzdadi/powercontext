"""运行配置，全部来自环境变量（docker-compose.yml 中给出了默认值）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# MINIMAX_REGION 对应的 Anthropic 兼容接口基址；也可以直接用 MINIMAX_BASE_URL 指定
MINIMAX_BASE_URLS = {"cn": "https://api.minimax.cn/anthropic", "intl": "https://api.minimax.io/anthropic"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    home: Path
    project_dir: Path
    samples_dir: Path
    runs_dir: Path
    seekdb_host: str
    seekdb_port: int
    seekdb_user: str
    seekdb_password: str
    seekdb_database: str
    powercontext_url: str
    minimax_base_url: str
    minimax_model: str
    minimax_api_key: str
    code_version: str

    @classmethod
    def load(cls) -> "Settings":
        home = Path(_env("SDD_HOME") or os.getcwd()).resolve()
        return cls(
            home=home,
            project_dir=(home / (_env("SDD_PROJECT_DIR") or "project")).resolve(),
            samples_dir=(home / (_env("SDD_SAMPLES_DIR") or "samples")).resolve(),
            runs_dir=(home / (_env("SDD_RUNS_DIR") or "runs")).resolve(),
            seekdb_host=_env("SDD_SEEKDB_HOST", "127.0.0.1"),
            seekdb_port=int(_env("SDD_SEEKDB_PORT", "2881")),
            seekdb_user=_env("SDD_SEEKDB_USER", "root"),
            seekdb_password=_env("SDD_SEEKDB_PASSWORD"),
            seekdb_database=_env("SDD_SEEKDB_DATABASE", "sdd"),
            powercontext_url=_env("SDD_POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/"),
            minimax_base_url=(_env("MINIMAX_BASE_URL") or MINIMAX_BASE_URLS.get(_env("MINIMAX_REGION", "cn").lower(), MINIMAX_BASE_URLS["cn"])).rstrip("/"),
            minimax_model=_env("MINIMAX_MODEL", "MiniMax-M3.1-Flash"),
            minimax_api_key=_env("MINIMAX_API_KEY"),
            code_version=_env("SDD_CODE_VERSION", "unknown"),
        )

    def rel(self, path: Path) -> str:
        """相对 home 的路径，用于输出和记录。"""
        try:
            return str(path.resolve().relative_to(self.home))
        except ValueError:
            return str(path)
