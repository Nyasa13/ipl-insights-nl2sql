"""Shared fixtures: a DuckDB database built from the synthetic data, using the SAME cleaning code and the
SAME views.sql as production, so SQL / view bugs show up without needing PostgreSQL."""
from __future__ import annotations

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

ROOT = Path(__file__).resolve().parents[1]


class DuckRunner:
    """Duck-typed stand-in for app.db.Database."""

    def __init__(self, con):
        self.con = con

    def run(self, sql):
        cur = self.con.execute(sql)
        cols = [d[0] for d in cur.description]
        return cols, [tuple(r) for r in cur.fetchall()]

    def fetch_df(self, sql):
        return self.con.execute(sql).df()

    def ping(self):
        return True


@pytest.fixture(scope="session")
def duck():
    from db.load_data import clean_deliveries, clean_matches
    from scripts.make_synthetic_data import make

    raw_m, raw_d = make(seasons=range(2012, 2025), matches_per_season=30)
    matches = clean_matches(raw_m)
    deliveries = clean_deliveries(raw_d, set(matches["match_id"]))
    con = duckdb.connect(":memory:")
    con.register("matches_df", matches)
    con.register("deliveries_df", deliveries)
    con.execute("CREATE TABLE matches AS SELECT * FROM matches_df")
    con.execute("CREATE TABLE deliveries AS SELECT * FROM deliveries_df")
    con.execute((ROOT / "db" / "views.sql").read_text())
    return DuckRunner(con)
