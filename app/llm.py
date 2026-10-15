"""One thin LLM wrapper. Every provider here speaks the OpenAI chat API, so swapping models is an env change."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app.config import get_settings

CACHE_DIR = Path(".cache/llm")


class LLMClient:
    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None,
                 cache: bool | None = None):
        s = get_settings()
        self.model = model or s.llm_model
        if not self.model:
            raise RuntimeError("Set LLM_MODEL in .env to a model your provider currently offers.")
        self.cache = s.llm_cache if cache is None else cache
        self._api_key = api_key or s.llm_api_key
        self._base_url = base_url or s.llm_base_url
        self._client = None
        self.calls = 0  # network calls actually made (cache hits excluded)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=60)
        return self._client

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / f"{key}.json"

    def complete(self, system: str, user: str, temperature: float = 0.0, max_tokens: int = 700) -> str:
        key = hashlib.sha256(json.dumps([self.model, system, user, temperature]).encode()).hexdigest()
        if self.cache and self._cache_path(key).exists():
            return json.loads(self._cache_path(key).read_text())["text"]

        delay, last = 2.0, None
        for _ in range(5):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, temperature=temperature, max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
                self.calls += 1
                out = resp.choices[0].message.content or ""
                if self.cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    self._cache_path(key).write_text(json.dumps({"text": out}))
                return out
            except Exception as e:  # rate limits, timeouts, 5xx
                last = e
                name = type(e).__name__
                if name in ("AuthenticationError", "BadRequestError", "NotFoundError", "PermissionDeniedError"):
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30)
        raise RuntimeError(f"LLM call failed after retries: {last}")
