import numpy as np
import pandas as pd

from app.anomaly import batting_anomalies, bowling_anomalies, detect_anomalies


def _frame(values, name="V Kohli"):
    n = len(values)
    return pd.DataFrame({
        "batter": name, "match_id": range(n), "season": 2023,
        "date": pd.date_range("2023-04-01", periods=n), "runs": values, "balls_faced": 30, "strike_rate": 120.0,
    })


def test_spike_is_flagged_and_normal_is_not():
    rng = np.random.default_rng(0)
    base = list(rng.integers(20, 40, 15)) + [120]
    out = detect_anomalies(_frame(base), "batter", "runs")
    assert list(out["runs"]) == [120]
    assert out.iloc[0]["z"] > 2.5


def test_needs_history_before_flagging():
    assert detect_anomalies(_frame([5, 5, 200]), "batter", "runs").empty


def test_pct_threshold_blocks_statistically_odd_but_small_changes():
    # tiny variance => huge z for a small absolute change; pct_thresh stops the alert
    vals = [100.0, 100.1, 99.9, 100.0, 100.2, 99.8, 100.0, 100.1, 100.0, 112.0]
    out = detect_anomalies(_frame(vals), "batter", "runs", pct_thresh=0.5)
    assert out.empty


def test_batting_wrapper_adds_plain_language_explanation():
    base = [25, 30, 28, 35, 22, 31, 27, 33, 29, 26, 24, 101]
    out = batting_anomalies(_frame(base), season=2023)
    assert len(out) == 1
    assert "101 runs" in out.iloc[0]["explanation"] and "standard deviations" in out.iloc[0]["explanation"]


def test_bowling_flags_expensive_spell():
    n = 14
    df = pd.DataFrame({
        "bowler": "JJ Bumrah", "match_id": range(n), "season": 2023, "date": pd.date_range("2023-04-01", periods=n),
        "balls": 24, "runs_conceded": [27, 30, 26, 29, 28, 31, 27, 26, 30, 28, 29, 27, 28, 62],
        "wickets": 1,
    })
    df["economy"] = 6.0 * df["runs_conceded"] / df["balls"]
    out = bowling_anomalies(df, season=2023)
    assert len(out) == 1 and out.iloc[0]["direction"] == "high"
