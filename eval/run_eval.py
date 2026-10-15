"""Run the ablation and measure execution accuracy.

    python -m eval.run_eval --split dev  --stages zero_shot schema_aware      # tune prompts on DEV only
    python -m eval.run_eval --split test --stages all                         # final numbers, run once

Per-question records go to eval/results/<stage>_<split>.json; a markdown table goes to
eval/results/summary_<split>.md (paste it in the README).
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict

from app.prompts import STAGES, load_few_shot
from eval.common import RESULTS_DIR, build_pipeline, check_no_leakage, load_questions
from eval.compare import results_match

TIERS = ["easy", "medium", "hard", "tricky"]


def run_stage(pipe, db, stage: str, questions: list[dict], sleep: float = 0.0) -> list[dict]:
    records = []
    for q in questions:
        rec = {"id": q["id"], "difficulty": q["difficulty"], "question": q["question"], "gold_sql": q["gold_sql"]}
        try:
            gold = db.run(q["gold_sql"])
        except Exception as e:
            raise SystemExit(f"Gold SQL for {q['id']} fails on your database: {e}")
        t0 = time.perf_counter()
        gen = pipe.generate(q["question"], stage)
        rec.update(latency_ms=round((time.perf_counter() - t0) * 1000), generated_sql=gen.sql, error=gen.error,
                   attempts=len(gen.attempts), hints=gen.hints, blocked=gen.blocked)
        rec["correct"] = bool(gen.ok and results_match(gold, (gen.columns, gen.rows), q.get("ordered", False)))
        records.append(rec)
        print(f"  [{stage}] {q['id']:>4} {'OK ' if rec['correct'] else 'FAIL'} {q['question'][:70]}")
        if sleep:
            time.sleep(sleep)
    return records


def accuracy(records: list[dict]) -> dict:
    by = defaultdict(lambda: [0, 0])
    for r in records:
        for k in (r["difficulty"], "overall"):
            by[k][0] += r["correct"]
            by[k][1] += 1
    return {k: v for k, v in by.items()}


def to_markdown(table: dict[str, dict]) -> str:
    head = "| Stage | " + " | ".join(TIERS) + " | **Overall** |\n|---|" + "---|" * (len(TIERS) + 1)
    lines = [head]
    for stage, acc in table.items():
        cells = [f"{acc[t][0]}/{acc[t][1]}" if t in acc else "-" for t in TIERS]
        o = acc["overall"]
        lines.append(f"| {stage} | " + " | ".join(cells) + f" | **{o[0]}/{o[1]} ({100 * o[0] / o[1]:.1f}%)** |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["dev", "test", "all"])
    ap.add_argument("--stages", nargs="+", default=["all"])
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (smoke test)")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between questions (free-tier rate limits)")
    args = ap.parse_args()
    stages = STAGES if args.stages == ["all"] else args.stages

    questions = load_questions(args.split)
    if args.limit:
        questions = questions[: args.limit]
    leaks = check_no_leakage(load_few_shot(), questions)
    if leaks:
        raise SystemExit("Few-shot leakage into the evaluation set:\n  " + "\n  ".join(leaks))

    pipe, db = build_pipeline()
    RESULTS_DIR.mkdir(exist_ok=True)
    table = {}
    for stage in stages:
        print(f"== {stage} ({len(questions)} questions, split={args.split})")
        recs = run_stage(pipe, db, stage, questions, args.sleep)
        (RESULTS_DIR / f"{stage}_{args.split}.json").write_text(json.dumps(recs, indent=2, default=str))
        table[stage] = accuracy(recs)
        lat = sorted(r["latency_ms"] for r in recs)
        print(f"   accuracy {table[stage]['overall']}  median SQL latency {lat[len(lat) // 2]} ms")

    md = to_markdown(table)
    (RESULTS_DIR / f"summary_{args.split}.md").write_text(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()
