"""Application service layer — runs the graph and persists app state.

This is the "DynamoDB" role in Couchbase: per-conversation sessions, intermediate
steps/logs, and granular citations are written to KV collections. Combined with
the CouchbaseSaver (graph state), this gives the article's resume-from-failure
behaviour at both the graph and application level.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .couchbase_client import kv_upsert, kv_get
from .graph import get_graph


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    return f"sess-{uuid.uuid4().hex[:12]}"


def _persist(session_id: str, question: str, result: dict[str, Any]) -> None:
    # session snapshot (app state)
    kv_upsert(settings.coll_sessions, session_id, {
        "type": "session",
        "session_id": session_id,
        "question": question,
        "answer": result.get("answer", ""),
        "needs_clarification": result.get("needs_clarification", False),
        "updated_at": _now(),
    })
    # intermediate steps (transparency / observability)
    kv_upsert(settings.coll_logs, f"{session_id}::steps", {
        "type": "log",
        "session_id": session_id,
        "steps": result.get("steps", []),
        "sql": result.get("sql"),
        "created_at": _now(),
    })
    # granular citations
    kv_upsert(settings.coll_citations, f"{session_id}::citations", {
        "type": "citations",
        "session_id": session_id,
        "citations": result.get("citations", []),
        "created_at": _now(),
    })


def run_chat(question: str, session_id: str | None = None,
             clarification_answer: str | None = None) -> dict[str, Any]:
    session_id = session_id or _new_session_id()

    # If the user is answering a clarifying question, fold it into the query so
    # the second pass proceeds (fail-fast then resume).
    effective_q = question
    if clarification_answer:
        effective_q = f"{question} (clarification: {clarification_answer})"

    config = {"configurable": {"thread_id": session_id, "checkpoint_ns": ""}}
    graph = get_graph(checkpointer=True)
    final: dict[str, Any] = graph.invoke({"question": effective_q, "session_id": session_id}, config)

    result = {
        "session_id": session_id,
        "answer": final.get("answer", ""),
        "needs_clarification": final.get("needs_clarification", False),
        "clarify_question": final.get("clarify_question", ""),
        "citations": final.get("citations", []),
        "steps": final.get("steps", []),
        "sql": final.get("sql"),
        "rows": final.get("rows", []),
        "recommended_sources": final.get("recommended_sources", []),
    }
    _persist(session_id, effective_q, result)
    return result


def resume_chat(session_id: str) -> dict[str, Any]:
    """Resume a failed/interrupted run from its last checkpoint — skips steps
    that already succeeded (the article's user-initiated retry)."""
    config = {"configurable": {"thread_id": session_id, "checkpoint_ns": ""}}
    graph = get_graph(checkpointer=True)
    # invoking with None resumes from the persisted checkpoint
    final = graph.invoke(None, config)
    result = {
        "session_id": session_id,
        "answer": final.get("answer", ""),
        "needs_clarification": final.get("needs_clarification", False),
        "clarify_question": final.get("clarify_question", ""),
        "citations": final.get("citations", []),
        "steps": final.get("steps", []),
        "sql": final.get("sql"),
        "rows": final.get("rows", []),
        "recommended_sources": final.get("recommended_sources", []),
    }
    _persist(session_id, final.get("question", ""), result)
    return result


def get_session(session_id: str) -> dict[str, Any] | None:
    sess = kv_get(settings.coll_sessions, session_id)
    if not sess:
        return None
    logs = kv_get(settings.coll_logs, f"{session_id}::steps") or {}
    cites = kv_get(settings.coll_citations, f"{session_id}::citations") or {}
    sess["steps"] = logs.get("steps", [])
    sess["citations"] = cites.get("citations", [])
    return sess
