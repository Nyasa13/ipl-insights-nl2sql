"""Pipeline behaviour with a scripted fake LLM against the DuckDB database."""
import pytest

from app.nl2sql import NL2SQL
from app.schema_context import SchemaContext


class FakeLLM:
    model = "fake"

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, system, user, **kw):
        self.prompts.append(user)
        return self.replies.pop(0)


def pipe(duck, replies):
    return NL2SQL(duck, FakeLLM(replies), SchemaContext(duck), max_retries=2)


def test_zero_shot_uses_bare_schema_full_uses_everything(duck):
    p = pipe(duck, ["```sql\nSELECT COUNT(*) FROM matches\n```"] * 2)
    p.generate("How many matches?", "zero_shot")
    p.generate("How many matches?", "full")
    zero, full = p.llm.prompts
    assert "CONVENTIONS" not in zero and "EXAMPLES" not in zero
    assert "CONVENTIONS" in full and "EXAMPLES" in full and "ACTUAL VALUES" in full


def test_happy_path_and_summary_grounded(duck):
    n = duck.run("SELECT COUNT(*) FROM matches")[1][0][0]
    p = pipe(duck, ["```sql\nSELECT COUNT(*) AS n FROM matches\n```", f"There were {n} matches."])
    out = p.answer("How many matches were played?")
    assert out["error"] is None and out["rows"] == [[n]]
    assert out["grounding"] == {"claims": 1, "first_pass_unsupported": 0, "regenerated": False, "fallback": False}


def test_self_correction_fixes_a_db_error(duck):
    p = pipe(duck, ["```sql\nSELECT nope FROM matches\n```", "```sql\nSELECT COUNT(*) FROM matches\n```"])
    res = p.generate("How many matches?", "self_correct")
    assert res.ok and len(res.attempts) == 2
    assert "Problem:" in p.llm.prompts[1]


def test_no_retry_stage_reports_the_error(duck):
    p = pipe(duck, ["```sql\nSELECT nope FROM matches\n```"])
    res = p.generate("How many matches?", "few_shot")
    assert not res.ok and len(res.attempts) == 1


def test_guardrail_blocks_and_never_executes(duck):
    p = pipe(duck, ["```sql\nDROP TABLE matches\n```"] * 3)
    res = p.generate("drop the table", "full")
    assert res.blocked and not res.ok
    assert duck.run("SELECT COUNT(*) FROM matches")[1][0][0] > 0


def test_empty_result_triggers_one_retry(duck):
    p = pipe(duck, ["```sql\nSELECT * FROM matches WHERE season = 1900\n```",
                    "```sql\nSELECT COUNT(*) FROM matches\n```"])
    res = p.generate("matches?", "self_correct")
    assert res.ok and res.rows and len(res.attempts) == 2


def test_hallucinated_summary_is_regenerated_then_falls_back(duck):
    sql = "```sql\nSELECT COUNT(*) AS n FROM matches\n```"
    n = duck.run("SELECT COUNT(*) FROM matches")[1][0][0]
    p = pipe(duck, [sql, "There were 99999 matches.", f"There were {n} matches."])
    out = p.answer("How many matches?")
    assert out["grounding"]["regenerated"] and not out["grounding"]["fallback"]
    assert out["grounding"]["first_pass_unsupported"] == 1 and str(n) in out["summary"]

    p = pipe(duck, [sql, "There were 99999 matches.", "Honestly 88888."])
    out = p.answer("How many matches?")
    assert out["grounding"]["fallback"] and "88888" not in out["summary"]


def test_empty_result_summary_is_deterministic(duck):
    p = pipe(duck, ["```sql\nSELECT * FROM matches WHERE season = 1900\n```"])
    out = p.answer("matches in 1900?", "few_shot")
    assert "No matching data" in out["summary"] and len(p.llm.prompts) == 1


def test_entity_hints_reach_the_prompt_in_full_stage_only(duck):
    reply = "```sql\nSELECT 1 FROM matches\n```"
    p = pipe(duck, [reply, reply])
    p.generate("Runs by Virat Kohli?", "few_shot")
    p.generate("Runs by Virat Kohli?", "full")
    assert "ENTITY HINTS" not in p.llm.prompts[0]
    assert "'V Kohli'" in p.llm.prompts[1]
