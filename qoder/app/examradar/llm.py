"""OpenAI 兼容 chat completions 客户端（Ollama /v1 等）。

- 未配置（LLM_BASE_URL / LLM_MODEL 为空）时所有功能走无模型路径。
- qwen3.5 是推理模型：system prompt 追加 /no_think 关闭 thinking，
  解析时再剥一次 <think>…</think>，双保险。
- 同一模型每次调用带同样的 num_ctx（Ollama OpenAI 兼容层接受的 options），
  避免每次重载模型。
- 小模型对写在每一段消息里的具体要求比只写在 system 里的规则更听话，
  所以生成 / 判分的约束同时写进 system 和 user 消息。
"""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx

from .config import get_settings


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self):
        s = get_settings()
        self.base_url = (s.llm_base_url or "").rstrip("/")
        self.api_key = s.llm_api_key
        self.model = s.llm_model
        self.num_ctx = s.llm_num_ctx

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def chat(self, messages: list[dict], *, temperature: float = 0.3,
             json_mode: bool = False, timeout: float = 120.0) -> str:
        """返回 assistant 消息文本（已剥 thinking）。"""
        if not self.configured:
            raise LLMError("LLM 未配置")
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if self.num_ctx:
            body["options"] = {"num_ctx": self.num_ctx}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise LLMError(f"LLM 网络错误: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"LLM 响应结构异常: {json.dumps(data, ensure_ascii=False)[:300]}") from e
        return strip_thinking(content)

    def chat_json(self, messages: list[dict], *, temperature: float = 0.2,
                  timeout: float = 120.0) -> dict:
        """要求 JSON 输出并做容错解析。失败抛 LLMError。"""
        text = self.chat(messages, temperature=temperature, json_mode=True, timeout=timeout)
        parsed = parse_json_tolerant(text)
        if not isinstance(parsed, dict):
            raise LLMError("LLM 输出不是 JSON 对象")
        return parsed


def strip_thinking(text: str) -> str:
    """剥掉 qwen3.5 的 <think>…</think>（含未闭合的残段）。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    text = re.sub(r"</think>", "", text)
    return text.strip()


def parse_json_tolerant(text: str) -> Optional[object]:
    """容错解析：剥 markdown 代码围栏，找第一个平衡的 {...} 或 [...]。"""
    if not text:
        return None
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except Exception:
                        break
        # 括号不平衡：截到最后一个 closer 试试
        last = cleaned.rfind(closer)
        if last > start:
            try:
                return json.loads(cleaned[start:last + 1])
            except Exception:
                pass
    return None


def get_llm_client() -> LLMClient:
    return LLMClient()
