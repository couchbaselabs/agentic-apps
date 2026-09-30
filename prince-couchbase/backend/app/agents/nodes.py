"""LangGraph node functions — one per PRINCE stage.

Each node reads and returns a partial PrinceState. Context engineering: every
node builds its own minimal context. The graph (graph.py) wires them together
and the CouchbaseSaver persists state after each.
"""
from __future__ import annotations

import re
from typing import Any

from ..llm import llm
from ..config import settings
from .. import prompts
from . import rag, text_to_sql

MAX_REFLECT = 2  # cap reflection loops (article: iterative but bounded)


# ------------------------------------------------------------------ clarify
def clarify(state: dict[str, Any]) -> dict[str, Any]:
    q = state["question"]
    out = llm.json(
        [{"role": "user", "content": prompts.CLARIFY.format(question=q)}],
        fast=True, task="clarify",
    )
    steps = state.get("steps", [])
    steps.append({"step": "clarify", "needs_clarification": out.get("needs_clarification", False)})
    return {
        "needs_clarification": bool(out.get("needs_clarification", False)),
        "clarify_question": out.get("question", ""),
        "recommended_sources": out.get("recommended_sources", []),
        "steps": steps,
    }


# ------------------------------------------------------------------ think/plan
def think_plan(state: dict[str, Any]) -> dict[str, Any]:
    q = state["question"]
    out = llm.json(
        [{"role": "user", "content": prompts.ROUTE.format(question=q)}],
        fast=True, task="route",
    )
    steps = state.get("steps", [])
    steps.append({"step": "think_plan", "use_rag": out.get("use_rag"),
                  "use_sql": out.get("use_sql"), "plan": out.get("plan", "")})
    return {
        "use_rag": bool(out.get("use_rag", True)),
        "use_sql": bool(out.get("use_sql", False)),
        "plan": out.get("plan", ""),
        "steps": steps,
    }


# ------------------------------------------------------------------ researcher
def researcher(state: dict[str, Any]) -> dict[str, Any]:
    q = state["question"]
    steps = state.get("steps", [])
    update: dict[str, Any] = {}

    # follow-up queries from a prior reflection loop get merged into the search
    followups = state.get("followup_queries", []) or []
    rag_query = q if not followups else f"{q} " + " ".join(followups)

    if state.get("use_rag", True):
        r = rag.run(rag_query, steps)
        update["chunks"] = r["chunks"]
        update["_rag_answer"] = r["answer"]

    if state.get("use_sql", False):
        s = text_to_sql.run(q, steps)
        update["sql"] = s["sql"]
        update["rows"] = s["rows"]
        update["sql_error"] = s["error"]

    update["steps"] = steps
    return update


# ------------------------------------------------------------------ reflection
def reflection(state: dict[str, Any]) -> dict[str, Any]:
    q = state["question"]
    steps = state.get("steps", [])
    context = _context_for_reflection(state)
    out = llm.json(
        [{"role": "user", "content": prompts.REFLECTION.format(question=q, context=context)}],
        task="reflection",
    )
    count = state.get("reflect_count", 0) + 1
    sufficient = bool(out.get("sufficient", True)) or count > MAX_REFLECT
    steps.append({"step": "reflection", "sufficient": sufficient,
                  "missing": out.get("missing", []), "loop": count})
    return {
        "sufficient": sufficient,
        "missing": out.get("missing", []),
        "followup_queries": out.get("followup_queries", []) if not sufficient else [],
        "reflect_count": count,
        "steps": steps,
    }


# ------------------------------------------------------------------ writer
def writer(state: dict[str, Any]) -> dict[str, Any]:
    q = state["question"]
    steps = state.get("steps", [])
    context = _context_for_writer(state)
    answer = llm.complete(
        [{"role": "user", "content": prompts.WRITER.format(question=q, context=context)}],
        task="writer",
    )
    citations = extract_citations(answer, state)
    steps.append({"step": "writer", "n_citations": len(citations)})
    return {"answer": answer, "citations": citations, "steps": steps}


# ------------------------------------------------------------------ helpers
def _context_for_reflection(state: dict[str, Any]) -> str:
    parts = []
    for c in state.get("chunks", []) or []:
        parts.append(f"[cite:{c['chunk_id']}] {c['text']}")
    if state.get("rows"):
        parts.append("STRUCTURED ROWS: " + str(state["rows"])[:1500])
    return "CONTEXT:\n" + ("\n".join(parts) if parts else "(no evidence retrieved)")


def _context_for_writer(state: dict[str, Any]) -> str:
    parts = []
    for c in state.get("chunks", []) or []:
        parts.append(
            f"[cite:{c['chunk_id']}] (study {c['study_id']}, p.{c.get('page')}, "
            f"{c.get('parent_section','')}): {c['text']}"
        )
    rows = state.get("rows") or []
    if rows:
        parts.append("STRUCTURED RESULTS (SQL++):")
        for r in rows[:settings.sql_max_rows]:
            sid = r.get("study_id", "")
            parts.append(f"[study:{sid}] {r}")
        if state.get("sql"):
            parts.append(f"(generated SQL++: {state['sql']})")
    return "\n".join(parts) if parts else "(no evidence retrieved)"


_CITE_RE = re.compile(r"\[cite:([^\]]+)\]")
_STUDY_RE = re.compile(r"\[study:([^\]]+)\]")


def extract_citations(answer: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the granular citation objects the UI hovers over: chunk_id, study,
    page, section, exact quote."""
    by_chunk = {c["chunk_id"]: c for c in (state.get("chunks", []) or [])}
    citations: list[dict[str, Any]] = []
    seen = set()
    for cid in _CITE_RE.findall(answer):
        if cid in seen:
            continue
        seen.add(cid)
        c = by_chunk.get(cid, {})
        citations.append({
            "chunk_id": cid,
            "study_id": c.get("study_id"),
            "page": c.get("page"),
            "parent_section": c.get("parent_section"),
            "quote": (c.get("text", "")[:280] + "…") if c.get("text") else None,
        })
    for sid in _STUDY_RE.findall(answer):
        key = f"study:{sid}"
        if key in seen:
            continue
        seen.add(key)
        citations.append({"study_id": sid, "chunk_id": None, "quote": None})
    return citations
