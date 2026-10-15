from decimal import Decimal

from eval.compare import results_match

G = (["batter", "runs"], [("V Kohli", 973), ("JC Buttler", 863)])


def test_identical():
    assert results_match(G, G)


def test_column_names_and_order_ignored():
    gen = (["r", "who"], [(973, "V Kohli"), (863, "JC Buttler")])
    assert results_match(G, gen)


def test_extra_columns_allowed():
    gen = (["batter", "runs", "sixes"], [("V Kohli", 973, 38), ("JC Buttler", 863, 45)])
    assert results_match(G, gen)


def test_missing_column_fails():
    assert not results_match(G, (["batter"], [("V Kohli",), ("JC Buttler",)]))


def test_row_order_only_matters_when_ordered():
    gen = (["batter", "runs"], [("JC Buttler", 863), ("V Kohli", 973)])
    assert results_match(G, gen, ordered=False)
    assert not results_match(G, gen, ordered=True)


def test_wrong_value_and_wrong_rowcount_fail():
    assert not results_match(G, (["batter", "runs"], [("V Kohli", 973), ("JC Buttler", 800)]))
    assert not results_match(G, (["batter", "runs"], [("V Kohli", 973)]))


def test_numeric_types_and_case():
    gold = (["a", "b"], [(Decimal("8.26"), "Mumbai Indians")])
    gen = (["x", "y"], [(8.3, "mumbai indians ")])
    assert results_match(gold, gen)


def test_row_alignment_is_respected():
    gold = (["a", "b"], [(1, "x"), (2, "y")])
    gen = (["a", "b"], [(1, "y"), (2, "x")])  # same columns, wrong pairing
    assert not results_match(gold, gen)
