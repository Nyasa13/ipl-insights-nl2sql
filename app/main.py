"""FastAPI backend.   uvicorn app.main:app --reload"""
from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.prompts import STAGES
from app.service import EXAMPLE_QUESTIONS, Service, get_service

app = FastAPI(title="IPL Insights", version="1.0.0",
              description="Natural-language analytics over IPL data with SQL guardrails and grounded summaries.")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    stage: Literal[tuple(STAGES)] = "full"  # type: ignore[valid-type]


def client_id(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


@app.get("/health")
def health(svc: Service = Depends(get_service)):
    return {"status": "ok", "database": svc.db.ping(), "model": svc.pipeline.llm.model}


@app.get("/examples")
def examples():
    return {"questions": EXAMPLE_QUESTIONS}


@app.post("/ask")
def ask(req: AskRequest, request: Request, svc: Service = Depends(get_service)):
    allowed, msg = svc.limiter.check(client_id(request))
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)
    try:
        return svc.pipeline.answer(req.question.strip(), req.stage)
    except RuntimeError as e:  # LLM provider failure
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")


@app.get("/anomalies")
def anomalies(kind: Literal["batting", "bowling"] = "batting", season: int | None = Query(None, ge=2008, le=2100),
              top: int = Query(15, ge=1, le=50), svc: Service = Depends(get_service)):
    return {"kind": kind, "season": season, "results": svc.anomalies(kind, season, top)}
