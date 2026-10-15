# 🏏 IPL Insights: natural-language analytics with guardrails

Ask questions about IPL cricket in plain English. The system writes PostgreSQL, **validates it**, runs it
**read-only**, and answers in a sentence, a table and a chart, **checking that every number in the answer
appears in the query result**. It also flags unusual player performances with a rolling Z-score.

> **Live demo:** _add link_  ·  **Eval results:** see [Results](#results)

```
 question ──► entity linking ──► prompt (schema + conventions + few-shot) ──► LLM ──► SQL
                                                                                      │
          ┌───────────────── retry with the error / empty-result feedback ◄──────────┤
          │                                                                          ▼
          │                                  sqlglot guardrail (1 SELECT, allowlist, no side-effect functions, LIMIT)
          │                                                                          │ regenerated SQL only
          │                                                                          ▼
          └──────────────────────────────────────────────  PostgreSQL (SELECT-only role, read-only txn, 5 s timeout)
                                                                                      │ rows
                                                          LLM summary ──► grounding check ──► regenerate ──► deterministic fallback
                                                                                      ▼
                                                              FastAPI  /ask  ──►  Streamlit UI (table, chart, SQL, ✅ verified)
```

## What is in the repo

| Path | What it does |
|---|---|
| `db/schema.sql`, `db/views.sql`, `db/load_data.py` | Schema, indexes, analytics views (`ball_facts` etc.), cleaning + loading + read-only role |
| `app/validator.py` | sqlglot guardrail: single SELECT, table allowlist, forbidden functions, row cap, comment stripping |
| `app/prompts.py`, `app/schema_context.py`, `app/entities.py` | Prompt stages, live schema values, name linking ("Virat Kohli" → `V Kohli`, "RCB" → full team name) |
| `app/nl2sql.py` | Pipeline with ablation stages and self-correction |
| `app/grounding.py` | Numeric grounding check for LLM summaries |
| `app/anomaly.py` | Rolling Z-score + %-change anomaly detector for batting and bowling |
| `app/main.py`, `app/ratelimit.py` | FastAPI (`/ask`, `/anomalies`, `/health`), per-client and daily rate limits |
| `ui/streamlit_app.py` | Question box, example buttons, collapsible SQL, auto-chart, anomaly tab |
| `eval/` | Gold question set, execution-accuracy runner, failure analysis, adversarial tests, grounding eval |
| `tests/` | 170 offline tests (the gold SQL is executed on DuckDB with synthetic data) |
| `Dockerfile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/ci.yml` | Run, deploy, CI |

## Quick start

```bash
git clone <your-repo> && cd ipl-insights-nl2sql
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then fill in the LLM key + model (see below)

pytest -q                       # 170 tests, no database or API key needed
```

### 1. Database

```bash
docker compose up -d db
# (a) just try it with fake data:
docker compose --profile init run --rm loader python -m db.load_data --synthetic
# (b) real data: download the Kaggle "IPL Complete Dataset (2008-2024)" and put matches.csv and
#     deliveries.csv in data/raw/, then:
docker compose --profile init run --rm loader
```

The loader cleans team names (franchise renames), derives `season` from the match date, renumbers overs to
1..20, creates the tables/indexes/views, and creates a **SELECT-only role** `ipl_readonly`. If your CSV
column names differ, adjust `COLUMN_ALIASES` in `db/load_data.py`.

> ⚠️ Synthetic data is random. Never quote numbers computed on it.

### 2. LLM

Edit `.env`: set `LLM_PROVIDER` (`groq`, `gemini`, `ollama`, `openai`), the matching API key, and
`LLM_MODEL` to **a model that provider currently offers** (free-tier model lists change, so check their docs).
Everything uses the OpenAI-compatible API, so switching providers is an env change.

### 3. Run

```bash
docker compose up -d api ui     # UI http://localhost:8501   API docs http://localhost:8000/docs
# or without Docker:
uvicorn app.main:app --reload &
streamlit run ui/streamlit_app.py
```

## Evaluation (this is where your resume numbers come from)

`eval/questions.json` has 40 questions in four tiers (easy / medium / hard / tricky) with gold SQL, split into
**dev (8)** for tuning prompts and **test (32)** for the final numbers. 40 is a *starter set*: **extend it to
60-100** with questions you write yourself, and verify every gold query by hand on your real data.

Rules that keep the numbers honest:
1. Tune prompts only on `--split dev`. Run `--split test` once at the end.
2. Few-shot examples must not resemble test questions (the runner refuses to start if they do).
3. Gold SQL has no tie-breaking surprises on real data; fix questions whose answer is a tie.

```bash
python -m eval.run_eval --split dev  --stages all --sleep 2     # while developing
python -m eval.run_eval --split test --stages all --sleep 2     # final run -> eval/results/summary_test.md
python -m eval.adversarial                                       # safety: 24 hostile SQL strings + 12 hostile prompts
python -m eval.grounding_eval --split test                       # unsupported numeric claims before/after the check
python -m eval.failure_analysis export --stage full --split test # then label the CSV by hand
python -m eval.failure_analysis chart  --stage full --split test # -> docs/failure_breakdown.png
```

**Metric:** execution accuracy. Generated and gold SQL are both executed; results match if row counts agree and
every gold column appears in the generated output with identical values (column names/order ignored, row order
ignored unless the question is marked `ordered`, numbers compared at 1 decimal). See `eval/compare.py`.

**Stages (ablation):** `zero_shot` (bare table DDL) → `schema_aware` (+ annotated views, conventions, real
values) → `few_shot` (+ 8 examples) → `self_correct` (+ retry on DB error / empty result) → `full` (+ entity linking).

### Results

_Fill in from `eval/results/summary_test.md` after your real run._

| Stage | easy | medium | hard | tricky | **Overall** |
|---|---|---|---|---|---|
| zero_shot | | | | | |
| schema_aware | | | | | |
| few_shot | | | | | |
| self_correct | | | | | |
| full | | | | | |

Other numbers to record: adversarial inputs blocked (`eval.adversarial`), unsupported numeric claims before/after
grounding (`eval.grounding_eval`), median latency (printed by `run_eval`), number of matches/deliveries loaded.

## Safety design (defence in depth)

1. **Parse, don't trust:** sqlglot parses the LLM output; the *regenerated* SQL is what runs (comments stripped).
2. Exactly one `SELECT`/`WITH`; no DML/DDL/`COPY`/`SELECT INTO`/`FOR UPDATE`; no writable CTEs.
3. Table **allowlist** (no `pg_*`, `information_schema`, schema-qualified names, or table-valued functions); denylist of dangerous functions (`pg_sleep`, `pg_read_file`, `generate_series`, ...).
4. Automatic `LIMIT` (and clamping of larger limits).
5. DB layer: SELECT-only role, `default_transaction_read_only=on`, `statement_timeout=5s`.
6. API: per-client rate limit + global daily cap so strangers cannot burn your free LLM quota.

## Deploying

Free-tier terms change, so check each provider's current limits.
1. Create a free Postgres (e.g. Neon or Supabase). Run the loader once from your laptop with
   `DATABASE_URL_ADMIN` pointing at it and a strong `READONLY_PASSWORD`.
2. Deploy the repo as a Docker web service (`render.yaml` for Render; Hugging Face Spaces also works with the
   Docker SDK, set app port 7860). Set `DATABASE_URL_RO` (read-only role!), the LLM key/model as **secrets**.
   `docker/start.sh` runs the API internally and Streamlit publicly.
3. Put the live link at the top of this README and in your resume header.

## Known limitations (say these in interviews, it shows judgement)

- Player names are stored as initials + surname; entity linking covers common cases but not every alias.
- The "best X" convention (minimum balls) is a documented design choice, not ground truth.
- Venue names in the raw data are inconsistent; queries use `ILIKE`.
- LLM output is probabilistic; the guardrail guarantees *safety*, not *correctness*.
- The grounding check verifies numbers appear in the result; it does not verify the prose reasoning.
- Rate limiting is in-memory (single process).

## Resume bullets (replace X/Y with your measured numbers)

> **IPL Insights: NL-to-SQL Analytics Assistant** | Python • FastAPI • PostgreSQL • LLM • Docker  
> Live: [link] • Code: [github link]
> - Built a natural-language analytics assistant over X IPL matches (Y deliveries); schema-aware prompting, few-shot examples, entity linking and SQL self-correction raised execution accuracy from X% to Y% on a held-out N-question gold set.
> - Enforced safety with a sqlglot validator, read-only DB role and timeouts (A/A adversarial inputs blocked); a numeric grounding check on generated summaries cut unsupported claims from X to Y; added Z-score anomaly detection for outlier performances.
