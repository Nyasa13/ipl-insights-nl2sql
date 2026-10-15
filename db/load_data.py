"""Clean the Kaggle IPL CSVs and load them into PostgreSQL.

Usage:
    python -m db.load_data --matches data/raw/matches.csv --deliveries data/raw/deliveries.csv
    python -m db.load_data --synthetic            # small fake dataset, for trying the pipeline

Environment:
    DATABASE_URL_ADMIN   owner connection (creates tables, loads data)
    READONLY_PASSWORD    password for the least-privilege role the app connects with

Expected raw columns follow the "IPL Complete Dataset (2008-2024)" on Kaggle
(matches.csv: id, date, venue, team1, ...; deliveries.csv: match_id, inning, batter,
batsman_runs, ...). Older dumps that call the columns `batsman` / `batsman_runs` are
handled through COLUMN_ALIASES. Adjust there if your copy differs.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent

# Canonical team names (franchise renames collapsed to the current name).
TEAM_ALIASES = {
    "Delhi Daredevils": "Delhi Capitals",
    "Kings XI Punjab": "Punjab Kings",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Rising Pune Supergiants": "Rising Pune Supergiant",
    "Rising Pune Supergiant": "Rising Pune Supergiant",
}

COLUMN_ALIASES = {
    "matches": {"id": "match_id"},
    "deliveries": {
        "batsman": "batter",
        "batsman_runs": "batter_runs",
        "over": "over_no",
    },
}

MATCH_COLS = [
    "match_id", "season", "date", "city", "venue", "match_type", "team1", "team2",
    "toss_winner", "toss_decision", "winner", "result", "result_margin",
    "target_runs", "target_overs", "super_over", "player_of_match",
]
DELIVERY_COLS = [
    "match_id", "inning", "batting_team", "bowling_team", "over_no", "ball", "batter",
    "bowler", "non_striker", "batter_runs", "extra_runs", "total_runs", "extras_type",
    "is_wicket", "player_dismissed", "dismissal_kind", "fielder",
]


def _blank_to_none(s: pd.Series) -> pd.Series:
    s = s.astype("object")
    s = s.where(s.notna(), None)
    return s.map(lambda v: None if v is None or str(v).strip() in ("", "NA", "NaN", "nan", "None") else str(v).strip())


def _canon_team(s: pd.Series) -> pd.Series:
    return s.map(lambda v: TEAM_ALIASES.get(v, v) if v is not None else None)


def clean_matches(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=COLUMN_ALIASES["matches"]).copy()
    for c in MATCH_COLS:
        if c not in df.columns:
            df[c] = None
    for c in ["city", "venue", "match_type", "team1", "team2", "toss_winner", "toss_decision",
              "winner", "result", "super_over", "player_of_match"]:
        df[c] = _blank_to_none(df[c])
    for c in ["team1", "team2", "toss_winner", "winner"]:
        df[c] = _canon_team(df[c])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "team1", "team2"])
    # Kaggle labels seasons like "2007/08" or "2020/21"; the calendar year of the match is unambiguous.
    df["season"] = df["date"].dt.year.astype(int)
    df["date"] = df["date"].dt.date
    df["match_id"] = df["match_id"].astype(int)
    for c in ["result_margin", "target_runs", "target_overs"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.drop_duplicates(subset=["match_id"])
    return df[MATCH_COLS].reset_index(drop=True)


def clean_deliveries(df: pd.DataFrame, valid_match_ids: set[int] | None = None) -> pd.DataFrame:
    df = df.rename(columns=COLUMN_ALIASES["deliveries"]).copy()
    for c in DELIVERY_COLS:
        if c not in df.columns:
            df[c] = None
    for c in ["batting_team", "bowling_team", "batter", "bowler", "non_striker", "extras_type",
              "player_dismissed", "dismissal_kind", "fielder"]:
        df[c] = _blank_to_none(df[c])
    for c in ["batting_team", "bowling_team"]:
        df[c] = _canon_team(df[c])
    for c in ["match_id", "inning", "ball", "batter_runs", "extra_runs", "total_runs", "is_wicket"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    # The raw file numbers overs 0..19; the database uses 1..20 so "over 20" means the last over.
    df["over_no"] = pd.to_numeric(df["over_no"], errors="coerce").astype(int) + 1
    df = df.dropna(subset=["batter", "bowler", "batting_team", "bowling_team"])
    if valid_match_ids is not None:
        df = df[df["match_id"].isin(valid_match_ids)]
    return df[DELIVERY_COLS].reset_index(drop=True)


# --------------------------------------------------------------------------- Postgres side

def _psycopg_dsn(sqlalchemy_url: str) -> str:
    from sqlalchemy.engine import make_url
    return make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(hide_password=False)


def create_readonly_role(conn, db_name: str, password: str) -> None:
    from psycopg2 import sql
    with conn.cursor() as cur:
        cur.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ipl_readonly') "
                    "THEN CREATE ROLE ipl_readonly LOGIN; END IF; END $$;")
        cur.execute(sql.SQL("ALTER ROLE ipl_readonly WITH LOGIN PASSWORD {}").format(sql.Literal(password)))
        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO ipl_readonly").format(sql.Identifier(db_name)))
        cur.execute("GRANT USAGE ON SCHEMA public TO ipl_readonly")
        cur.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ipl_readonly")
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO ipl_readonly")  # includes views
        cur.execute("ALTER ROLE ipl_readonly SET default_transaction_read_only = on")
        cur.execute("ALTER ROLE ipl_readonly SET statement_timeout = '5s'")
    conn.commit()


def load_to_postgres(matches: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    import psycopg2
    from sqlalchemy import create_engine
    admin_url = os.environ["DATABASE_URL_ADMIN"]
    ro_password = os.environ.get("READONLY_PASSWORD", "ipl_readonly")

    conn = psycopg2.connect(_psycopg_dsn(admin_url))
    with conn.cursor() as cur:
        cur.execute((ROOT / "schema.sql").read_text())
    conn.commit()

    engine = create_engine(admin_url)
    matches.to_sql("matches", engine, if_exists="append", index=False, method="multi", chunksize=2000)
    deliveries.to_sql("deliveries", engine, if_exists="append", index=False, method="multi", chunksize=5000)

    with conn.cursor() as cur:
        cur.execute((ROOT / "views.sql").read_text())
        cur.execute("ANALYZE")
    conn.commit()
    from sqlalchemy.engine import make_url
    create_readonly_role(conn, make_url(admin_url).database, ro_password)
    conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", default="data/raw/matches.csv")
    ap.add_argument("--deliveries", default="data/raw/deliveries.csv")
    ap.add_argument("--synthetic", action="store_true", help="generate and load a small fake dataset")
    ap.add_argument("--dry-run", action="store_true", help="clean and print stats, do not touch the database")
    args = ap.parse_args()

    if args.synthetic:
        from scripts.make_synthetic_data import make
        raw_m, raw_d = make()
    else:
        raw_m, raw_d = pd.read_csv(args.matches), pd.read_csv(args.deliveries, low_memory=False)

    matches = clean_matches(raw_m)
    deliveries = clean_deliveries(raw_d, set(matches["match_id"]))
    print(f"matches: {len(matches):,}  seasons: {matches['season'].min()}-{matches['season'].max()}  "
          f"deliveries: {len(deliveries):,}")
    print("teams:", sorted(set(matches['team1']) | set(matches['team2'])))
    if not args.dry_run:
        load_to_postgres(matches, deliveries)
        print("Loaded. Read-only role: ipl_readonly")


if __name__ == "__main__":
    main()
