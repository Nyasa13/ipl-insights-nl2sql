"""Wires the pieces together once per process."""
from __future__ import annotations

import time
from functools import lru_cache

from app.anomaly import batting_anomalies, bowling_anomalies
from app.config import get_settings
from app.db import Database
from app.llm import LLMClient
from app.nl2sql import NL2SQL
from app.ratelimit import RateLimiter
from app.schema_context import SchemaContext

EXAMPLE_QUESTIONS = [
    "Top 5 run scorers in 2023",
    "Which bowler has the best death-over economy since 2020 (min 200 balls)?",
    "How many matches did RCB win after losing the toss?",
    "Which batter has hit the most sixes in IPL history?",
    "Who has dismissed Virat Kohli the most times?",
]


class Service:
    def __init__(self):
        s = get_settings()
        self.settings = s
        self.db = Database(s.database_url_ro, s.statement_timeout_ms, s.max_rows)
        self.schema_ctx = SchemaContext(self.db)
        self.pipeline = NL2SQL(self.db, LLMClient(), self.schema_ctx, s.max_retries, s.max_rows)
        self.limiter = RateLimiter(s.rate_limit_per_min, s.daily_ask_cap)
        self._anom_cache: dict = {}

    def anomalies(self, kind: str, season: int | None, top: int) -> list[dict]:
        key = (kind, season, top)
        hit = self._anom_cache.get(key)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
        if kind == "batting":
            df = self.db.fetch_df("SELECT match_id, season, date, batter, runs, balls_faced, strike_rate FROM player_match_batting")
            out = batting_anomalies(df, season, top)
            cols = ["date", "batter", "runs", "balls_faced", "z", "pct_change", "explanation"]
        else:
            df = self.db.fetch_df("SELECT match_id, season, date, bowler, balls, runs_conceded, wickets, economy FROM player_match_bowling")
            out = bowling_anomalies(df, season, top)
            cols = ["date", "bowler", "economy", "wickets", "z", "explanation"]
        records = []
        for r in out[cols].to_dict("records") if len(out) else []:
            r["date"] = str(r["date"])[:10]
            for k in ("z", "pct_change", "economy"):
                if k in r:
                    r[k] = round(float(r[k]), 2)
            records.append(r)
        self._anom_cache[key] = (time.time(), records)
        return records


@lru_cache
def get_service() -> Service:
    return Service()
