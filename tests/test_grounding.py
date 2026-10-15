from app.grounding import check_grounding, extract_numbers, template_summary

COLS, ROWS = ["batter", "runs"], [("V Kohli", 973), ("JC Buttler", 863), ("Q de Kock", 508)]
Q = "Top 3 run scorers in 2016"


def test_extract_numbers_handles_commas_decimals_percent_and_ignores_tokens():
    got = [(r, v) for r, v, _ in extract_numbers("1,234 runs, SR 142.5, 28% of T20 games")]
    assert got == [("1,234", 1234.0), ("142.5", 142.5), ("28%", 28.0)]


def test_grounded_summary():
    s = "V Kohli led with 973 runs, ahead of JC Buttler on 863 in 2016."
    r = check_grounding(s, Q, COLS, ROWS)
    assert r.grounded and r.claims == 3


def test_unsupported_number_is_flagged():
    r = check_grounding("V Kohli scored 980 runs.", Q, COLS, ROWS)
    assert r.unsupported == ["980"]


def test_derived_numbers_are_flagged():
    r = check_grounding("Together they scored 1,836 runs.", Q, COLS, ROWS)
    assert not r.grounded


def test_rounding_tolerance():
    r = check_grounding("Economy was 8.3.", "Best economy?", ["economy"], [(8.26,)])
    assert r.grounded
    r = check_grounding("Economy was 8.4.", "Best economy?", ["economy"], [(8.26,)])
    assert not r.grounded


def test_numbers_inside_date_cells_count():
    r = check_grounding("It happened on 21 May 2023.", "When?", ["date"], [("2023-05-21",)])
    assert r.grounded


def test_rank_positions_and_row_count_allowed():
    assert check_grounding("The top 3 are listed.", "who", ["a"], [(1,), (1,), (1,)]).grounded


def test_template_summary_is_always_grounded():
    for rows in ([("V Kohli", 973)], ROWS, []):
        s = template_summary(Q, COLS, rows)
        assert check_grounding(s, Q, COLS, rows).grounded
