"""SQL guardrail. The LLM output is never executed as written: it is parsed with sqlglot,
checked against an allowlist, and the *regenerated* SQL is what we run (this defeats
comment / parser-differential tricks)."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {
    "matches", "deliveries", "ball_facts", "batting_by_season", "bowling_by_season",
    "player_match_batting", "player_match_bowling",
}
FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Copy,
    exp.Merge, exp.Into, exp.Lock, exp.Set, exp.Use, exp.Grant, exp.TruncateTable, exp.Transaction,
)
FORBIDDEN_FUNC_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting", "txid_",
                           "query_to_", "xpath", "generate_series", "inet_", "version", "current_user",
                           "session_user", "current_database", "current_schema")


class SQLValidationError(ValueError):
    pass


def _func_names(tree: exp.Expression):
    for f in tree.find_all(exp.Func):
        if isinstance(f, exp.Anonymous):
            yield str(f.name).lower()
        else:
            yield f.sql_name().lower()


def validate_sql(sql: str, max_rows: int = 500) -> str:
    """Return a safe, normalised SELECT (with a LIMIT) or raise SQLValidationError."""
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.SqlglotError as e:
        raise SQLValidationError(f"SQL could not be parsed: {str(e)[:200]}") from e
    if len(statements) != 1:
        raise SQLValidationError("Exactly one statement is allowed.")
    tree = statements[0]
    for n in tree.walk():
        n.comments = None  # drop comments entirely

    if not isinstance(tree, exp.Query):
        raise SQLValidationError("Only SELECT queries are allowed.")
    for node in tree.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, FORBIDDEN_NODES):
            raise SQLValidationError(f"Forbidden operation: {type(n).__name__}.")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if not isinstance(t.this, exp.Identifier):
            raise SQLValidationError("Table-valued functions are not allowed.")
        if t.args.get("db") or t.args.get("catalog"):
            raise SQLValidationError("Schema-qualified tables are not allowed.")
        name = t.name.lower()
        if name not in ALLOWED_TABLES and name not in cte_names:
            raise SQLValidationError(f"Table '{t.name}' is not allowed.")

    for fname in _func_names(tree):
        if fname.startswith(FORBIDDEN_FUNC_PREFIXES):
            raise SQLValidationError(f"Function '{fname}' is not allowed.")

    # enforce a row cap on the outermost query
    if isinstance(tree, exp.Select):
        lim = tree.args.get("limit")
        ok_literal = lim is not None and isinstance(lim.expression, exp.Literal) and lim.expression.is_int
        if lim is None or not ok_literal:
            tree = tree.limit(max_rows)
        elif int(lim.expression.this) > max_rows:
            tree = tree.limit(max_rows)
    else:
        tree = exp.select("*").from_(tree.subquery("_q")).limit(max_rows)
    return tree.sql(dialect="postgres")
