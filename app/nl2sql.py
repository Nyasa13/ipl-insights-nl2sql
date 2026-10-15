"""The NL -> SQL -> answer pipeline. `stage` selects how much help the LLM gets, which is what the
evaluation ablation compares (zero_shot -> schema_aware -> few_shot -> self_correct -> full)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.entities import EntityLinker
from app.grounding import check_grounding, template_summary
from app.prompts import (STAGE_FLAGS, SUMMARY_SYSTEM, SYSTEM_SQL, build_prompt, build_retry_prompt,
                         build_summary_prompt, extract_sql, load_few_shot)
from app.validator import SQLValidationError, validate_sql


@dataclass
class GenResult:
    question: str
    stage: str
    sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    error: str | None = None
    blocked: bool = False          # rejected by the SQL guardrail
    attempts: list = field(default_factory=list)
    hints: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


class NL2SQL:
    def __init__(self, db, llm, schema_ctx=None, max_retries: int = 2, max_rows: int = 500, few_shot=None):
        self.db, self.llm, self.schema_ctx = db, llm, schema_ctx
        self.max_retries, self.max_rows = max_retries, max_rows
        self.few_shot = few_shot if few_shot is not None else load_few_shot()
        self._linker: EntityLinker | None = None

    @property
    def linker(self) -> EntityLinker:
        if self._linker is None:
            self._linker = EntityLinker(self.schema_ctx.players() if self.schema_ctx else [])
        return self._linker

    # ------------------------------------------------------------------ SQL generation
    def generate(self, question: str, stage: str = "full") -> GenResult:
        flags = STAGE_FLAGS[stage]
        res = GenResult(question=question, stage=stage)
        dynamic = self.schema_ctx.text() if (flags["schema"] and self.schema_ctx) else ""
        res.hints = self.linker.hints(question) if flags["entity"] else []
        base = build_prompt(question, flags, dynamic, res.hints, self.few_shot)

        prompt, tries = base, (self.max_retries if flags["retry"] else 0)
        empty_retry_used = False
        for attempt in range(tries + 1):
            raw = self.llm.complete(SYSTEM_SQL, prompt)
            sql = extract_sql(raw)
            res.sql, res.error, res.blocked = sql, None, False
            rec = {"attempt": attempt, "sql": sql}
            try:
                safe = validate_sql(sql, self.max_rows)
                res.columns, res.rows = self.db.run(safe)
                rec["rows"] = len(res.rows)
                if not res.rows and flags["retry"] and not empty_retry_used and attempt < tries:
                    empty_retry_used = True
                    rec["problem"] = "empty result"
                    res.attempts.append(rec)
                    prompt = build_retry_prompt(base, sql, "The query returned 0 rows. Check filter values "
                                                "(exact team/player spelling, season, phase) and join logic.")
                    continue
                res.attempts.append(rec)
                return res
            except SQLValidationError as e:
                res.error, res.blocked = f"Blocked by SQL guardrail: {e}", True
                rec["problem"] = res.error
            except Exception as e:  # database error
                res.error = str(getattr(e, "orig", e)).strip().split("\n")[0][:300]
                rec["problem"] = res.error
            res.attempts.append(rec)
            prompt = build_retry_prompt(base, sql, res.error)
        return res

    # ------------------------------------------------------------------ summary + grounding
    def summarize(self, question: str, columns: list, rows: list) -> tuple[str, dict]:
        info = {"claims": 0, "first_pass_unsupported": 0, "regenerated": False, "fallback": False}
        if not rows:
            return template_summary(question, columns, rows), info
        try:
            first = self.llm.complete(SUMMARY_SYSTEM, build_summary_prompt(question, columns, rows, len(rows)))
            chk = check_grounding(first, question, columns, rows)
            info["claims"], info["first_pass_unsupported"] = chk.claims, len(chk.unsupported)
            if chk.grounded:
                return first.strip(), info
            info["regenerated"] = True
            second = self.llm.complete(SUMMARY_SYSTEM, build_summary_prompt(
                question, columns, rows, len(rows), feedback=", ".join(chk.unsupported)))
            if check_grounding(second, question, columns, rows).grounded:
                return second.strip(), info
        except Exception:
            pass
        info["fallback"] = True
        return template_summary(question, columns, rows), info

    def answer(self, question: str, stage: str = "full") -> dict:
        t0 = time.perf_counter()
        gen = self.generate(question, stage)
        out = {
            "question": question, "stage": stage, "sql": gen.sql, "columns": gen.columns,
            "rows": [list(r) for r in gen.rows], "row_count": len(gen.rows), "error": gen.error,
            "blocked": gen.blocked, "attempts": len(gen.attempts), "hints": gen.hints,
            "summary": None, "grounding": None,
        }
        if gen.ok:
            summary, info = self.summarize(question, gen.columns, gen.rows)
            out["summary"], out["grounding"] = summary, info
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        return out
