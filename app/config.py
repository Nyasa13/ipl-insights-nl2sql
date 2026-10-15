from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# OpenAI-compatible endpoints: one client library covers all of these.
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "openai": (None, "OPENAI_API_KEY"),
}


@dataclass(frozen=True)
class Settings:
    database_url_ro: str
    statement_timeout_ms: int
    max_rows: int
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str | None
    llm_cache: bool
    max_retries: int
    rate_limit_per_min: int
    daily_ask_cap: int


@lru_cache
def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    base_url, key_env = PROVIDERS.get(provider, (None, "LLM_API_KEY"))
    api_key = os.getenv("LLM_API_KEY") or (os.getenv(key_env) if key_env else "") or "not-needed"
    return Settings(
        database_url_ro=os.getenv("DATABASE_URL_RO", "postgresql+psycopg2://ipl_readonly:ipl_readonly@localhost:5432/ipl"),
        statement_timeout_ms=int(os.getenv("STATEMENT_TIMEOUT_MS", "5000")),
        max_rows=int(os.getenv("MAX_ROWS", "500")),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=api_key,
        llm_base_url=os.getenv("LLM_BASE_URL") or base_url,
        llm_cache=os.getenv("LLM_CACHE", "1") == "1",
        max_retries=int(os.getenv("SQL_MAX_RETRIES", "2")),
        rate_limit_per_min=int(os.getenv("RATE_LIMIT_PER_MIN", "8")),
        daily_ask_cap=int(os.getenv("DAILY_ASK_CAP", "500")),
    )
