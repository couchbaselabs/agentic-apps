"""FastAPI backend for PRINCE-on-Couchbase.

    uvicorn backend.app.main:app --reload --port 8000

Endpoints:
    POST /api/chat            run a question through the agentic graph
    POST /api/chat/{sid}/resume  resume a failed run from its last checkpoint
    GET  /api/session/{sid}   fetch a stored session (steps + citations)
    GET  /api/studies         list structured studies (SQL++)
    GET  /api/health          liveness + config summary
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .schema import ChatRequest, ChatResponse
from . import service
from .couchbase_client import query

app = FastAPI(title="PRINCE on Couchbase", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mock_llm": settings.mock_llm,
        "bucket": settings.cb_bucket,
        "scope": settings.cb_scope,
        "fts_vector_index": settings.cb_fts_vector_index,
        "model_strong": settings.llm_model_strong,
        "model_fast": settings.llm_model_fast,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(400, "question is required")
    result = service.run_chat(req.question, req.session_id, req.clarification_answer)
    return result


@app.post("/api/chat/{session_id}/resume", response_model=ChatResponse)
def resume(session_id: str):
    try:
        return service.resume_chat(session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"resume failed: {exc}")


@app.get("/api/session/{session_id}")
def session(session_id: str):
    s = service.get_session(session_id)
    if not s:
        raise HTTPException(404, "session not found")
    return s


@app.get("/api/studies")
def studies(species: str | None = None, compound: str | None = None, limit: int = 50):
    where, params = ["type = \"study\""], {}
    if species:
        where.append("species = $species")
        params["species"] = species.upper()
    if compound:
        where.append("compound = $compound")
        params["compound"] = compound
    rows = query(
        f"SELECT study_id, study_title, compound, species, route, study_type, year, "
        f"noael_mg_kg_day FROM {settings.coll_studies} WHERE {' AND '.join(where)} "
        f"ORDER BY year DESC LIMIT {int(limit)}",
        params or None,
    )
    return {"count": len(rows), "studies": rows}
