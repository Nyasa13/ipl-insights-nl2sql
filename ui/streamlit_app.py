"""Streamlit front end.   streamlit run ui/streamlit_app.py
Talks to the FastAPI backend (API_URL, default http://localhost:8000)."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chart_utils import choose_chart  # noqa: E402

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
EXAMPLES = [
    "Top 5 run scorers in 2023",
    "Which bowler has the best death-over economy since 2020 (min 200 balls)?",
    "How many matches did RCB win after losing the toss?",
    "Which batter has hit the most sixes in IPL history?",
    "Who has dismissed Virat Kohli the most times?",
]

st.set_page_config(page_title="IPL Insights", page_icon="🏏", layout="wide")


def client_ip() -> str:
    """Forward the visitor's address so the API rate-limits per visitor, not per UI container."""
    try:
        fwd = st.context.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    except Exception:
        pass
    if "sid" not in st.session_state:
        st.session_state["sid"] = uuid.uuid4().hex
    return st.session_state["sid"]


def api(method: str, path: str, **kw):
    headers = {"X-Forwarded-For": client_ip()}
    r = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=90, **kw)
    if r.status_code == 429:
        raise RuntimeError(r.json().get("detail", "Rate limited."))
    r.raise_for_status()
    return r.json()


def show_chart(df: pd.DataFrame):
    spec = choose_chart(df)
    if not spec:
        return
    kind, x, y = spec
    data = df.set_index(x)[[y]]
    (st.line_chart if kind == "line" else st.bar_chart)(data)


st.title("🏏 IPL Insights")
st.caption("Ask a question in plain English. The app writes SQL, checks it is safe, runs it read-only, "
           "and verifies every number in the answer against the result.")

ask_tab, anomaly_tab = st.tabs(["Ask a question", "Unusual performances"])

with ask_tab:
    cols = st.columns(len(EXAMPLES))
    for c, ex in zip(cols, EXAMPLES):
        if c.button(ex, use_container_width=True):
            st.session_state["q"] = ex
    question = st.text_input("Your question", key="q", max_chars=300,
                             placeholder="e.g. Who has the best strike rate in the powerplay?")
    if st.button("Ask", type="primary") and question.strip():
        try:
            with st.spinner("Writing and running SQL..."):
                out = api("POST", "/ask", json={"question": question.strip()})
        except Exception as e:
            st.error(str(e))
        else:
            if out.get("error"):
                st.warning(("Blocked by the safety guardrail: " if out["blocked"] else "Could not answer: ") + out["error"])
            else:
                st.subheader(out["summary"])
                g = out["grounding"] or {}
                if g.get("fallback"):
                    st.caption("✅ Numbers verified against the query result (plain summary used because the "
                               "AI draft contained unverifiable numbers).")
                else:
                    st.caption("✅ Every number in this answer was checked against the query result.")
                df = pd.DataFrame(out["rows"], columns=out["columns"])
                st.dataframe(df, use_container_width=True, hide_index=True)
                show_chart(df)
            with st.expander("Generated SQL"):
                st.code(out["sql"], language="sql")
                if out.get("hints"):
                    st.caption("Name hints used: " + "; ".join(out["hints"]))
                st.caption(f"{out['latency_ms']} ms · {out['attempts']} attempt(s) · {out['row_count']} row(s)")

with anomaly_tab:
    c1, c2, c3 = st.columns(3)
    kind = c1.selectbox("Type", ["batting", "bowling"])
    season = c2.number_input("Season", min_value=2008, max_value=2100, value=2024, step=1)
    top = c3.slider("How many", 5, 30, 15)
    if st.button("Find unusual performances"):
        try:
            res = api("GET", "/anomalies", params={"kind": kind, "season": int(season), "top": top})["results"]
        except Exception as e:
            st.error(str(e))
        else:
            if not res:
                st.info("Nothing unusual found for that season.")
            for r in res:
                st.markdown(f"- {r['explanation']}")
            st.caption("Method: rolling Z-score against the player's previous 10 matches, plus a %-change "
                       "threshold, so only changes that are both statistically and materially large are flagged.")
