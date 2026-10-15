"""Unusual-performance detection on per-match player stats.

Same idea as the Business Metrics Anomaly Detector project: a rolling Z-score against the player's own
recent history, AND a %-change threshold, so a spike must be both statistically unusual and materially large.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def detect_anomalies(
    df: pd.DataFrame, entity: str, value: str, *, date_col: str = "date", window: int = 10,
    min_periods: int = 5, z_thresh: float = 2.5, pct_thresh: float = 0.5, direction: str = "high",
    min_value: float | None = None,
) -> pd.DataFrame:
    """Flag rows whose `value` deviates from the entity's previous `window` observations.

    direction: 'high' | 'low' | 'both'. min_value: ignore flags whose absolute value is below this
    (e.g. a 12-run innings is not a story even if the player usually scores 3).
    """
    d = df.sort_values([entity, date_col]).copy()
    g = d.groupby(entity)[value]
    prior_mean = g.transform(lambda s: s.shift(1).rolling(window, min_periods=min_periods).mean())
    prior_std = g.transform(lambda s: s.shift(1).rolling(window, min_periods=min_periods).std())
    d["rolling_mean"] = prior_mean
    d["rolling_std"] = prior_std
    d["z"] = (d[value] - prior_mean) / prior_std.replace(0, np.nan)
    d["pct_change"] = (d[value] - prior_mean) / prior_mean.replace(0, np.nan)

    hi = (d["z"] >= z_thresh) & (d["pct_change"] >= pct_thresh)
    lo = (d["z"] <= -z_thresh) & (d["pct_change"] <= -pct_thresh)
    mask = {"high": hi, "low": lo, "both": hi | lo}[direction]
    if min_value is not None:
        mask &= d[value].abs() >= min_value
    out = d[mask].copy()
    out["direction"] = np.where(out["z"] >= 0, "high", "low")
    out["severity"] = out["z"].abs()
    return out.sort_values("severity", ascending=False)


def explain_batting(r) -> str:
    who, date = r["batter"], str(r["date"])[:10]
    return (f"{who} scored {int(r['runs'])} runs off {int(r['balls_faced'])} balls on {date}: "
            f"{abs(r['z']):.1f} standard deviations above his average of {r['rolling_mean']:.1f} "
            f"over his previous innings ({r['pct_change']:+.0%}).")


def explain_bowling(r) -> str:
    who, date = r["bowler"], str(r["date"])[:10]
    word = "above" if r["z"] > 0 else "below"
    quality = "an expensive spell" if r["z"] > 0 else "an unusually economical spell"
    return (f"{who} had {quality} on {date}: economy {r['economy']:.2f} "
            f"({int(r['runs_conceded'])} runs, {int(r['wickets'])} wkts in {int(r['balls'])} balls), "
            f"{abs(r['z']):.1f} standard deviations {word} his average of {r['rolling_mean']:.2f}.")


def batting_anomalies(df: pd.DataFrame, season: int | None = None, top: int = 20) -> pd.DataFrame:
    """df = player_match_batting rows."""
    out = detect_anomalies(df, "batter", "runs", direction="high", min_value=40)
    if season is not None:
        out = out[out["season"] == season]
    out = out.head(top).copy()
    out["explanation"] = out.apply(explain_batting, axis=1) if len(out) else []
    return out


def bowling_anomalies(df: pd.DataFrame, season: int | None = None, top: int = 20) -> pd.DataFrame:
    """df = player_match_bowling rows (spells of < 12 balls are ignored)."""
    df = df[df["balls"] >= 12]
    out = detect_anomalies(df, "bowler", "economy", direction="both")
    if season is not None:
        out = out[out["season"] == season]
    out = out.head(top).copy()
    out["explanation"] = out.apply(explain_bowling, axis=1) if len(out) else []
    return out
