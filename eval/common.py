from __future__ import annotations

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"


def load_questions(split: str = "test") -> list[dict]:
    qs = json.loads((EVAL_DIR / "questions.json").read_text())
    return qs if split == "all" else [q for q in qs if q["split"] == split]


def build_pipeline():
    from app.config import get_settings
    from app.db import Database
    from app.llm import LLMClient
    from app.nl2sql import NL2SQL
    from app.schema_context import SchemaContext
    s = get_settings()
    db = Database(s.database_url_ro, s.statement_timeout_ms, s.max_rows)
    return NL2SQL(db, LLMClient(), SchemaContext(db), s.max_retries, s.max_rows), db


def check_no_leakage(few_shot: list[dict], questions: list[dict], threshold: float = 80.0) -> list[str]:
    """Warn if any few-shot example is (nearly) identical to an evaluation question."""
    from rapidfuzz import fuzz
    problems = []
    for s in few_shot:
        for q in questions:
            score = fuzz.token_sort_ratio(s["question"].lower(), q["question"].lower())
            if score >= threshold or s["sql"].strip().lower() == q["gold_sql"].strip().lower():
                problems.append(f"few-shot '{s['question']}' ~ eval {q['id']} '{q['question']}' ({score:.0f})")
    return problems
