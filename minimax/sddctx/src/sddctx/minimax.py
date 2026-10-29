"""MiniMax 客户端：Anthropic 兼容的 Messages API（POST {base}/v1/messages），只用标准库。

国内站基址 https://api.minimax.cn/anthropic，模型默认 MiniMax-M3.1-Flash（Token Plan 可用）。
密钥只放在请求头 x-api-key 里，不写进任何记录。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504, 529}


class MiniMaxError(RuntimeError):
    pass


class MiniMaxClient:
    def __init__(self, api_key: str, base_url: str, model: str, *, timeout: float = 300, max_attempts: int = 5) -> None:
        if not api_key:
            raise MiniMaxError("没有配置 MINIMAX_API_KEY：在 .env 中填写密钥后重试，或使用 --replay 回放已记录的 MiniMax 修改")
        self.api_key = api_key
        self.url = base_url.rstrip("/") + "/v1/messages"
        self.model = model
        self.timeout = timeout
        self.max_attempts = max_attempts

    def create(self, *, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 16000) -> tuple[dict, float, int]:
        """返回 (响应 JSON, 耗时秒, 尝试次数)。"""
        body = json.dumps(
            {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages, "tools": tools},
            ensure_ascii=False,
        ).encode("utf-8")
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                self.url,
                data=body,
                method="POST",
                headers={"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read())
                base = data.get("base_resp") or {}
                if base.get("status_code") not in (None, 0):
                    raise MiniMaxError(f"MiniMax 返回错误 {base.get('status_code')}：{base.get('status_msg')}")
                return data, round(time.perf_counter() - started, 2), attempt
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:1000]
                last_error = f"HTTP {exc.code}：{detail}"
                if exc.code not in RETRY_STATUSES:
                    raise MiniMaxError(f"MiniMax 请求失败，{last_error}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < self.max_attempts:
                time.sleep(min(60, 5 * 2 ** (attempt - 1)))
        raise MiniMaxError(f"MiniMax 请求重试 {self.max_attempts} 次仍失败：{last_error}")
