"""Measure how often the LLM's first-draft summary contains numbers that are not in the query result,
versus the final summary the user sees after the grounding check (regenerate, then deterministic fallback).

    python -m eval.grounding_eval --split test

Reported numbers for the resume:
    unsupported claims in raw first-draft summaries  -> X of Y numeric claims (A% of summaries affected)
    unsupported claims in final summaries             -> verified again with check_grounding
"""
from __future__ import annotations

import argparse

from app.grounding import check_grounding
from eval.common import build_pipeline, load_questions


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--sleep", type=float, default=0.0)
    a = ap.parse_args()
    import time
    pipe, _ = build_pipeline()
    n = affected = claims = first_bad = final_bad = fallbacks = regen = 0
    for q in load_questions(a.split):
        out = pipe.answer(q["question"], "full")
        if not out["summary"] or not out["rows"]:
            continue
        n += 1
        g = out["grounding"]
        claims += g["claims"]
        first_bad += g["first_pass_unsupported"]
        affected += g["first_pass_unsupported"] > 0
        regen += g["regenerated"]
        fallbacks += g["fallback"]
        final = check_grounding(out["summary"], q["question"], out["columns"], [tuple(r) for r in out["rows"]])
        final_bad += len(final.unsupported)
        if a.sleep:
            time.sleep(a.sleep)
    print(f"answers with a summary: {n}")
    print(f"numeric claims in first-draft summaries: {claims}")
    print(f"  unsupported (first draft): {first_bad}  -> {affected}/{n} summaries affected")
    print(f"  regenerated: {regen}, deterministic fallback: {fallbacks}")
    print(f"  unsupported in FINAL summaries: {final_bad}")


if __name__ == "__main__":
    main()
