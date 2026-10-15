"""Every gold query and few-shot example must run on a real database (DuckDB here), pass the guardrail,
and the few-shot examples must not leak into the evaluation set."""
import json

import pytest

from app.prompts import load_few_shot
from app.validator import validate_sql
from eval.common import check_no_leakage, load_questions
from eval.compare import results_match

QUESTIONS = load_questions("all")


def test_question_file_is_well_formed():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    assert {q["difficulty"] for q in QUESTIONS} == {"easy", "medium", "hard", "tricky"}
    assert {q["split"] for q in QUESTIONS} == {"dev", "test"}


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_gold_sql_runs_and_passes_validator(duck, q):
    validate_sql(q["gold_sql"])
    cols, rows = duck.run(q["gold_sql"])
    assert cols  # executes; (synthetic data may legitimately yield 0 rows for threshold queries)


@pytest.mark.parametrize("s", load_few_shot(), ids=[s["question"][:30] for s in load_few_shot()])
def test_few_shot_sql_runs(duck, s):
    validate_sql(s["sql"])
    cols, rows = duck.run(s["sql"])
    assert cols


def test_no_few_shot_leakage():
    assert check_no_leakage(load_few_shot(), QUESTIONS) == []


def test_views_exclude_super_overs_and_count_legal_balls(duck):
    # no ball_facts row may come from inning 3/4
    assert duck.run("SELECT COUNT(*) FROM ball_facts WHERE inning > 2")[1][0][0] == 0
    # every regular innings has at most 20 overs worth of legal balls
    worst = duck.run("SELECT MAX(b) FROM (SELECT match_id, inning, SUM(is_legal_delivery) b FROM ball_facts GROUP BY 1, 2) x")[1][0][0]
    assert worst <= 120
    # bowler runs never exceed total runs
    assert duck.run("SELECT COUNT(*) FROM ball_facts WHERE bowler_runs > total_runs")[1][0][0] == 0
    # run outs are not credited to bowlers
    assert duck.run("SELECT COUNT(*) FROM ball_facts WHERE dismissal_kind='run out' AND is_bowler_wicket=1")[1][0][0] == 0


def test_loader_cleaning(duck):
    teams = {r[0] for r in duck.run("SELECT team1 FROM matches UNION SELECT team2 FROM matches")[1]}
    assert "Delhi Capitals" in teams and "Delhi Daredevils" not in teams
    assert "Royal Challengers Bengaluru" in teams and "Kings XI Punjab" not in teams
    assert duck.run("SELECT MIN(over_no), MAX(over_no) FROM deliveries")[1][0][0] == 1


@pytest.mark.parametrize("q", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_validator_rewrite_does_not_change_results(duck, q):
    """The guardrail executes its own regenerated SQL; it must return the same rows as the original."""
    raw = duck.run(q["gold_sql"])
    safe = duck.run(validate_sql(q["gold_sql"], max_rows=10_000))
    # sqlglot rewrites ROUND(x, 2) as ROUND(CAST(x AS DECIMAL), 2) (valid, and required, on PostgreSQL),
    # so compare values, not Python types.
    assert results_match(raw, safe, ordered=False)
