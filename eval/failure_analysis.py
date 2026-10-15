"""Manual failure analysis, same method as the RAGTruth project.

Step 1:  python -m eval.failure_analysis export --stage full --split test
         -> eval/results/failures_<stage>_<split>.csv with an `auto_hint` column. Open it and fill the
            `category` column by hand (one of CATEGORIES). Looking at each failure is the point.
Step 2:  python -m eval.failure_analysis chart --stage full --split test
         -> prints counts and saves docs/failure_breakdown.png for the README.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter

from eval.common import EVAL_DIR, RESULTS_DIR

CATEGORIES = ["wrong join", "wrong filter", "wrong metric definition", "hallucinated column/table",
              "wrong aggregation", "name/entity mismatch", "ambiguous question", "syntax/other"]


def auto_hint(rec: dict) -> str:
    err = (rec.get("error") or "").lower()
    if "does not exist" in err or "is not allowed" in err:
        return "hallucinated column/table"
    if "syntax" in err or "parse" in err:
        return "syntax/other"
    if rec.get("generated_sql") and "ilike" not in rec["generated_sql"].lower() and "'" in rec["generated_sql"]:
        return "check name/entity spelling"
    return ""


def export(stage: str, split: str) -> None:
    recs = json.loads((RESULTS_DIR / f"{stage}_{split}.json").read_text())
    fails = [r for r in recs if not r["correct"]]
    path = RESULTS_DIR / f"failures_{stage}_{split}.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "difficulty", "question", "gold_sql", "generated_sql", "error",
                                          "auto_hint", "category", "notes"])
        w.writeheader()
        for r in fails:
            w.writerow({**{k: r.get(k, "") for k in ["id", "difficulty", "question", "gold_sql", "generated_sql", "error"]},
                        "auto_hint": auto_hint(r), "category": "", "notes": ""})
    print(f"{len(fails)} failures -> {path}\nFill the 'category' column with one of: {CATEGORIES}")


def chart(stage: str, split: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = list(csv.DictReader(open(RESULTS_DIR / f"failures_{stage}_{split}.csv")))
    counts = Counter(r["category"].strip() or "unlabelled" for r in rows)
    for k, v in counts.most_common():
        print(f"{v:3d}  {k}")
    labels, vals = zip(*counts.most_common())
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.barh(labels[::-1], vals[::-1], color="#3b6ea5")
    ax.set_xlabel("failed questions")
    ax.set_title(f"Failure breakdown ({stage}, {split}, n={len(rows)})")
    fig.tight_layout()
    out = EVAL_DIR.parent / "docs" / "failure_breakdown.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150)
    print("saved", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "chart"])
    ap.add_argument("--stage", default="full")
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    (export if a.cmd == "export" else chart)(a.stage, a.split)
