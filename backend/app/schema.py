"""Shared state + API models."""
from __future__ import annotations

from typing import Any, Optional, TypedDict
from pydantic import BaseModel


# --- LangGraph shared state ---------------------------------------------------
class PrinceState(TypedDict, total=False):
    question: str
    session_id: str

    # clarify
    needs_clarification: bool
    clarify_question: str
    recommended_sources: list[str]

    # plan / routing
    use_rag: bool
    use_sql: bool
    plan: str

    # research outputs
    chunks: list[dict[str, Any]]      # retrieved RAG chunks
    sql: str
    rows: list[dict[str, Any]]        # Text-to-SQL++ rows
    sql_error: Optional[str]

    # reflection
    sufficient: bool
    missing: list[str]
    followup_queries: list[str]
    reflect_count: int

    # output
    answer: str
    citations: list[dict[str, Any]]
    steps: list[dict[str, Any]]       # intermediate steps (transparency)


# --- API models ---------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    # if the user is answering a clarifying question, they can pass it back:
    clarification_answer: Optional[str] = None


class Citation(BaseModel):
    chunk_id: Optional[str] = None
    study_id: Optional[str] = None
    page: Optional[int] = None
    parent_section: Optional[str] = None
    quote: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    needs_clarification: bool = False
    clarify_question: str = ""
    citations: list[Citation] = []
    steps: list[dict[str, Any]] = []
    sql: Optional[str] = None
    rows: list[dict[str, Any]] = []
    recommended_sources: list[str] = []
