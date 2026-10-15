"""Execution-accuracy comparison between gold and generated result sets.

Rules (documented so your README can state them):
  * row counts must match;
  * column NAMES and ORDER are ignored; every gold column must appear (as a column of identical values)
    somewhere in the generated result, so extra helpful columns do not count as errors;
  * row order is ignored unless the question is marked `ordered`;
  * numbers are compared at 1 decimal place, strings case-insensitively.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from itertools import islice, product


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float, Decimal)):
        return round(float(v), 1) + 0.0
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return str(v).strip().lower()


def results_match(gold: tuple, gen: tuple, ordered: bool = False) -> bool:
    _, g_rows = gold
    _, n_rows = gen
    if len(g_rows) != len(n_rows):
        return False
    if not g_rows:
        return True
    G = [tuple(norm(v) for v in r) for r in g_rows]
    N = [tuple(norm(v) for v in r) for r in n_rows]
    gc, nc = len(G[0]), len(N[0])
    if nc < gc:
        return False

    def col_key(rows, i):
        return sorted(repr(r[i]) for r in rows)

    gold_keys = [col_key(G, i) for i in range(gc)]
    gen_keys = [col_key(N, j) for j in range(nc)]
    cands = [[j for j in range(nc) if gen_keys[j] == gold_keys[i]] for i in range(gc)]
    if any(not c for c in cands):
        return False
    target = G if ordered else sorted(map(repr, G))
    for combo in islice(product(*cands), 5000):
        if len(set(combo)) != gc:
            continue
        proj = [tuple(r[j] for j in combo) for r in N]
        if (proj == G) if ordered else (sorted(map(repr, proj)) == target):
            return True
    return False
