"""
Minimal OpenAI-compatible chat client (no third-party deps) with retries and JSON extraction.

Works with OpenAI, DeepSeek, Gemini's OpenAI endpoint, Groq, OpenRouter, Ollama, LM Studio...
Configuration (first match wins):
  SUBTITLER_LLM_API_KEY  / OPENAI_API_KEY
  SUBTITLER_LLM_BASE_URL / OPENAI_BASE_URL      (default https://api.openai.com/v1)
  SUBTITLER_LLM_MODEL                            (default gpt-4o-mini)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional, Tuple


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, timeout: int = 120):
        self.api_key = api_key or os.environ.get("SUBTITLER_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("SUBTITLER_LLM_BASE_URL")
                         or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.environ.get("SUBTITLER_LLM_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    @property
    def available(self) -> bool:
        # local servers (Ollama / LM Studio) don't need a key
        return bool(self.api_key) or "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def chat(self, system: str, user: str, temperature: float = 0.2, retries: int = 3) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        last: Exception = RuntimeError("no attempt")
        for attempt in range(retries):
            req = urllib.request.Request(self.base_url + "/chat/completions",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (400, 401, 403, 404):
                    detail = e.read().decode("utf-8", "ignore")[:300]
                    raise RuntimeError(f"LLM request rejected ({e.code}): {detail}")
            except Exception as e:  # timeouts, connection resets, 5xx, 429
                last = e
            time.sleep(2 ** attempt)
        raise RuntimeError(f"LLM request failed after {retries} attempts: {last}")

    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> Any:
        return extract_json(self.chat(system, user, temperature))


def extract_json(raw: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and leading/trailing prose."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        for open_c, close_c in (("{", "}"), ("[", "]")):
            a, b = raw.find(open_c), raw.rfind(close_c)
            if a != -1 and b > a:
                try:
                    return json.loads(raw[a:b + 1])
                except json.JSONDecodeError:
                    continue
        raise


def to_id_map(obj: Any, value_key: str) -> Dict[int, str]:
    """Accept {"1": "..."} or [{"id": 1, value_key: "..."}] and return {1: "..."}."""
    out: Dict[int, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                v = v.get(value_key) or v.get("text") or v.get("translation") or ""
            try:
                out[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and "id" in item:
                v = item.get(value_key, item.get("text", item.get("translation", "")))
                out[int(item["id"])] = str(v)
    return out


def windows(n: int, size: int, context: int) -> Iterator[Tuple[int, int, int, int]]:
    """Yield (ctx_start, start, end, ctx_end) index windows for sliding-context batching."""
    for start in range(0, n, size):
        end = min(n, start + size)
        yield max(0, start - context), start, end, min(n, end + context)
