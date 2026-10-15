"""All prompt text lives here so ablation stages differ only in what they include."""
from __future__ import annotations

import json
import re
from pathlib import Path

FEW_SHOT_PATH = Path(__file__).parent / "few_shot.json"

SYSTEM_SQL = (
    "You are an expert PostgreSQL analyst. Reply with exactly one read-only SQL query inside a ```sql code "
    "block and nothing else. Never modify data."
)

# Baseline schema: just the two raw tables, no explanations.
BASE_DDL = """\
CREATE TABLE matches (match_id INT, season INT, date DATE, city TEXT, venue TEXT, match_type TEXT,
  team1 TEXT, team2 TEXT, toss_winner TEXT, toss_decision TEXT, winner TEXT, result TEXT,
  result_margin NUMERIC, target_runs NUMERIC, target_overs NUMERIC, super_over TEXT, player_of_match TEXT);
CREATE TABLE deliveries (match_id INT, inning INT, batting_team TEXT, bowling_team TEXT, over_no INT,
  ball INT, batter TEXT, bowler TEXT, non_striker TEXT, batter_runs INT, extra_runs INT, total_runs INT,
  extras_type TEXT, is_wicket INT, player_dismissed TEXT, dismissal_kind TEXT, fielder TEXT);"""

# Full, annotated schema + cricket conventions + views.
SCHEMA_DOC = """\
DATABASE: IPL (Indian Premier League cricket), PostgreSQL. Only these tables/views exist.

BASE TABLES
matches(match_id, season, date, city, venue, match_type, team1, team2, toss_winner, toss_decision,
        winner, result, result_margin, target_runs, target_overs, super_over, player_of_match)
  - season = calendar year (INT, e.g. 2023). winner is NULL when there was no result.
  - toss_decision: 'bat' or 'field'.
  - result: 'runs' = team batting FIRST won; 'wickets' = team CHASING (batting second) won;
    'tie'; 'no result'. result_margin = runs or wickets of the margin.
  - super_over: 'Y' / 'N'.
deliveries(match_id, inning, batting_team, bowling_team, over_no, ball, batter, bowler, non_striker,
           batter_runs, extra_runs, total_runs, extras_type, is_wicket, player_dismissed,
           dismissal_kind, fielder)
  - over_no is 1..20. inning 1/2 are regular innings, 3/4 are super overs.

VIEWS (PREFER THESE; they already apply the cricket rules)
ball_facts(match_id, season, date, venue, city, inning, batting_team, bowling_team, over_no, ball,
           batter, bowler, batter_runs, extra_runs, total_runs, extras_type, is_wicket,
           player_dismissed, dismissal_kind,
           bowler_runs, is_bowler_wicket, is_legal_delivery, is_batter_ball, phase)
  - one row per ball of regular innings only (super overs excluded), joined with match season/venue.
  - bowler_runs = runs charged to the bowler (excludes byes/leg byes/penalty).
  - is_bowler_wicket = 1 if the wicket counts for the bowler (excludes run outs, retirements).
  - is_legal_delivery = 1 unless wide/no-ball. is_batter_ball = 1 unless wide.
  - phase: 'powerplay' (overs 1-6), 'middle' (7-15), 'death' (16-20).
player_match_batting(match_id, season, date, batter, batting_team, runs, balls_faced, fours, sixes, strike_rate)
player_match_bowling(match_id, season, date, bowler, bowling_team, balls, runs_conceded, wickets, economy)
batting_by_season(season, batter, innings, balls_faced, runs, fours, sixes, strike_rate)
bowling_by_season(season, bowler, matches_bowled, balls, runs_conceded, wickets, economy)

CONVENTIONS
- Strike rate = 100.0 * runs / balls_faced. Economy = 6.0 * runs_conceded / legal balls. Use SUM over
  ball_facts columns, then divide, when aggregating across seasons (never average per-season rates).
- Bowler wickets: SUM(is_bowler_wicket), never SUM(is_wicket).
- "Death overs" = overs 16-20, "powerplay" = overs 1-6 (use phase or over_no).
- "Best" for a RATE statistic needs a minimum sample unless the question gives one:
  career-level questions: batters >= 500 balls faced, bowlers >= 300 legal balls;
  single-season questions: batters >= 100 balls faced, bowlers >= 60 legal balls.
- ROUND() in PostgreSQL needs numeric: write ROUND(100.0 * a / b, 2); never ROUND() a double precision value.
- Team names are the CURRENT franchise names (see list below). Player names are stored as initials + surname
  (e.g. 'V Kohli'); use the exact spelling from the hints/list, or ILIKE '%Surname%' if unsure.
- Match a team in matches with (team1 = X OR team2 = X). Use ILIKE '%word%' for venues.
- Output only what the question asks for (plus the sort key); add LIMIT for 'top N' questions."""

STAGES = ["zero_shot", "schema_aware", "few_shot", "self_correct", "full"]
STAGE_FLAGS = {
    #                    annotated schema, few-shot, self-correction, entity linking
    "zero_shot":    dict(schema=False, few_shot=False, retry=False, entity=False),
    "schema_aware": dict(schema=True,  few_shot=False, retry=False, entity=False),
    "few_shot":     dict(schema=True,  few_shot=True,  retry=False, entity=False),
    "self_correct": dict(schema=True,  few_shot=True,  retry=True,  entity=False),
    "full":         dict(schema=True,  few_shot=True,  retry=True,  entity=True),
}


def load_few_shot() -> list[dict]:
    return json.loads(FEW_SHOT_PATH.read_text())


def build_prompt(question: str, flags: dict, dynamic_context: str = "", hints: list[str] | None = None,
                 few_shot: list[dict] | None = None) -> str:
    parts = []
    if flags["schema"]:
        parts.append(SCHEMA_DOC)
        if dynamic_context:
            parts.append(dynamic_context)
    else:
        parts.append("Schema:\n" + BASE_DDL)
    if flags["few_shot"]:
        shots = few_shot if few_shot is not None else load_few_shot()
        ex = "\n\n".join(f"Question: {s['question']}\n```sql\n{s['sql'].strip()}\n```" for s in shots)
        parts.append("EXAMPLES\n" + ex)
    if hints:
        parts.append("ENTITY HINTS (exact names in the database):\n" + "\n".join(f"- {h}" for h in hints))
    parts.append(f"Question: {question}\nReturn one PostgreSQL SELECT query.")
    return "\n\n".join(parts)


def build_retry_prompt(base_prompt: str, prev_sql: str, problem: str) -> str:
    return (f"{base_prompt}\n\nYour previous query:\n```sql\n{prev_sql}\n```\nProblem: {problem}\n"
            "Fix it and return the corrected single SELECT query in a ```sql block.")


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql|postgresql)?\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(with|select)\b.*", text, re.S | re.I)
    return (m.group(0) if m else text).strip()


SUMMARY_SYSTEM = (
    "You write short, factual answers for cricket fans. Use ONLY facts and numbers that appear in the result "
    "table. Do not compute new numbers (no sums, averages, percentages or counts of your own). Do not mention "
    "SQL, tables or databases. 1-3 sentences."
)


def build_summary_prompt(question: str, columns: list[str], rows: list[tuple], total_rows: int,
                         feedback: str = "") -> str:
    shown = rows[:25]
    table = " | ".join(columns) + "\n" + "\n".join(" | ".join(str(v) for v in r) for r in shown)
    note = f"(showing first {len(shown)} of {total_rows} rows)\n" if total_rows > len(shown) else ""
    fb = f"\nYour previous answer used numbers not in the table: {feedback}. Rewrite using only table numbers." if feedback else ""
    return f"Question: {question}\n\nResult table:\n{note}{table}{fb}\n\nAnswer:"
