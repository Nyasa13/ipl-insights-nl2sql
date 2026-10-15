"""Pick a sensible chart for a result table (pure function, unit-tested)."""
from __future__ import annotations

import pandas as pd


def choose_chart(df: pd.DataFrame) -> tuple[str, str, str] | None:
    """Return (kind, x_col, y_col) with kind in {'bar', 'line'}, or None if a chart would not help."""
    if df is None or len(df) < 2 or df.shape[1] < 2 or len(df) > 60:
        return None
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    others = [c for c in df.columns if c not in numeric]
    if not numeric:
        return None
    y = numeric[-1]
    # a time-like numeric first column (season / year) -> line
    first = df.columns[0]
    if first in numeric and first != y and df[first].between(1990, 2100).all():
        return "line", first, y
    if others:
        x = others[0]
        if pd.api.types.is_datetime64_any_dtype(df[x]) or str(x).lower() in ("date", "season"):
            return "line", x, y
        return "bar", x, y
    return None
