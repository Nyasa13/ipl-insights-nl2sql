"""Read-only database access. Defence in depth: the app connects as a SELECT-only role,
every connection is forced read-only, and every statement has a timeout."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine, text


def jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


class Database:
    def __init__(self, url: str, timeout_ms: int = 5000, max_rows: int = 500):
        self.max_rows = max_rows
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            connect_args={"options": f"-c statement_timeout={timeout_ms} -c default_transaction_read_only=on"},
        )

    def run(self, sql: str) -> tuple[list[str], list[tuple]]:
        with self.engine.connect() as conn:
            res = conn.execute(text(sql))
            cols = list(res.keys())
            rows = [tuple(jsonable(v) for v in r) for r in res.fetchmany(self.max_rows)]
        return cols, rows

    def fetch_df(self, sql: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def ping(self) -> bool:
        try:
            self.run("SELECT 1")
            return True
        except Exception:
            return False
