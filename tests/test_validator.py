import pytest

from app.validator import SQLValidationError, validate_sql
from eval.adversarial import HOSTILE_SQL


@pytest.mark.parametrize("sql", HOSTILE_SQL)
def test_hostile_sql_is_blocked(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM matches",
    "SELECT batter, SUM(batter_runs) FROM ball_facts GROUP BY batter ORDER BY 2 DESC LIMIT 5;",
    "WITH t AS (SELECT team1 AS team FROM matches UNION ALL SELECT team2 FROM matches) SELECT team, COUNT(*) FROM t GROUP BY team",
    "SELECT * FROM batting_by_season WHERE season = 2023",
    "SELECT m.season, COUNT(*) FROM matches m JOIN deliveries d ON d.match_id = m.match_id GROUP BY m.season",
    "SELECT a FROM (SELECT 1 AS a) x",
    "SELECT season FROM matches UNION SELECT season FROM batting_by_season",
])
def test_valid_selects_pass(sql):
    out = validate_sql(sql)
    assert out.upper().lstrip().startswith(("SELECT", "WITH"))
    assert "LIMIT" in out.upper()


def test_limit_added_and_clamped():
    assert "LIMIT 500" in validate_sql("SELECT * FROM matches")
    assert "LIMIT 500" in validate_sql("SELECT * FROM matches LIMIT 100000")
    assert "LIMIT 5" in validate_sql("SELECT * FROM matches LIMIT 5")


def test_union_gets_wrapped_with_limit():
    out = validate_sql("SELECT season FROM matches UNION SELECT season FROM batting_by_season", 50)
    assert "LIMIT 50" in out


def test_comments_are_stripped_from_executed_sql():
    out = validate_sql("SELECT 1 FROM matches -- ; DROP TABLE matches")
    assert "DROP" not in out.upper()


def test_empty_and_garbage():
    for s in ["", "   ", "this is not sql at all ((("]:
        with pytest.raises(SQLValidationError):
            validate_sql(s)


def test_cte_named_like_a_real_table_is_fine_but_unknown_table_is_not():
    validate_sql("WITH x AS (SELECT * FROM matches) SELECT * FROM x")
    with pytest.raises(SQLValidationError):
        validate_sql("WITH x AS (SELECT * FROM matches) SELECT * FROM y")
