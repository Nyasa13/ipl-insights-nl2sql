import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.nl2sql import NL2SQL  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402
from app.service import get_service  # noqa: E402
from tests.test_pipeline import FakeLLM  # noqa: E402
from ui.chart_utils import choose_chart  # noqa: E402


class FakeService:
    def __init__(self, duck, replies, per_minute=100):
        self.db = duck
        self.pipeline = NL2SQL(duck, FakeLLM(replies), None, 2, 500)
        self.limiter = RateLimiter(per_minute, 1000)

    def anomalies(self, kind, season, top):
        return []


def client(duck, replies, per_minute=100):
    svc = FakeService(duck, replies, per_minute)
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app)


def test_health_and_examples(duck):
    c = client(duck, [])
    assert c.get("/health").json() == {"status": "ok", "database": True, "model": "fake"}
    assert len(c.get("/examples").json()["questions"]) >= 3


def test_ask_returns_answer(duck):
    n = duck.run("SELECT COUNT(*) FROM matches")[1][0][0]
    c = client(duck, ["```sql\nSELECT COUNT(*) AS n FROM matches\n```", f"There were {n} matches."])
    r = c.post("/ask", json={"question": "How many matches were played?"})
    assert r.status_code == 200 and r.json()["rows"] == [[n]] and r.json()["grounding"]["fallback"] is False


def test_ask_validates_input(duck):
    c = client(duck, [])
    assert c.post("/ask", json={"question": "x"}).status_code == 422
    assert c.post("/ask", json={"question": "valid question", "stage": "nope"}).status_code == 422


def test_rate_limit(duck):
    c = client(duck, ["```sql\nSELECT 1 FROM matches\n```", "One."] * 3, per_minute=1)
    assert c.post("/ask", json={"question": "first question"}).status_code == 200
    assert c.post("/ask", json={"question": "second question"}).status_code == 429


def test_blocked_sql_returns_error_not_data(duck):
    c = client(duck, ["```sql\nDROP TABLE matches\n```"] * 3)
    r = c.post("/ask", json={"question": "drop the matches table"}).json()
    assert r["blocked"] and r["rows"] == [] and r["summary"] is None


def test_choose_chart():
    bar = pd.DataFrame({"batter": ["a", "b", "c"], "runs": [3, 2, 1]})
    assert choose_chart(bar) == ("bar", "batter", "runs")
    line = pd.DataFrame({"season": [2020, 2021, 2022], "wins": [3, 4, 5]})
    assert choose_chart(line) == ("line", "season", "wins")
    assert choose_chart(pd.DataFrame({"n": [5]})) is None
    assert choose_chart(pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]})) is None
