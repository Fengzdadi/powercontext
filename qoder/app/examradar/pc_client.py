"""PowerContext client (minimal, for M1 health check only)."""
from __future__ import annotations

import httpx

from .config import get_settings


def check_powercontext() -> tuple[bool, str]:
    s = get_settings()
    try:
        resp = httpx.get(f"{s.powercontext_url}/health/ready", timeout=5)
        if resp.status_code == 200:
            return True, "ok"
        return False, f"status={resp.status_code}"
    except Exception as e:
        return False, str(e)
