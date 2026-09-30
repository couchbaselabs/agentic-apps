"""Deterministic mock LLM — powers the no-API-key demo/CI path.

When MOCK_LLM=true, every agent stage routes here instead of a network call.
Dispatch is by `task` label; outputs are heuristic but shaped exactly like the
real model's, so the full LangGraph pipeline runs end-to-end offline.

This is intentionally simple: it exists to prove the plumbing (Couchbase FTS +
vector + SQL++ + graph state + citations), not to replace a real LLM.
"""
from __future__ import annotations

import json
import re
from typing import Any

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "was",
    "were", "any", "following", "observed", "study", "give", "me", "show",
    "list", "what", "which", "is", "are", "do", "we", "have", "did", "does",
    "with", "did", "how", "many", "per", "all", "example", "examples", "done",
}


def _last_user(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return messages[-1].get("content", "") if messages else ""


def _keywords(text: str) -> list[str]:
    # keep medical multi-word phrases seen in the corpus
    phrases = [
        "eyes partially closed", "loose faeces", "hepatocellular hypertrophy",
        "QT interval", "squamous metaplasia", "thyroid follicular",
    ]
    found = [p for p in phrases if p.lower() in text.lower()]
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", text.lower())
    singles = [w for w in words if w not in STOPWORDS and len(w) > 3]
    # de-dup, preserve order
    seen, out = set(), []
    for w in found + singles:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:8]


def _study_id(text: str) -> str | None:
    m = re.search(r"\bT\d{6}-\d\b", text)
    return m.group(0) if m else None


def _species(text: str) -> str | None:
    for sp in ["RAT", "DOG", "MONKEY", "MOUSE"]:
        if re.search(rf"\b{sp}\b", text, re.I):
            return sp
    return None


def _compound(text: str) -> str | None:
    m = re.search(r"\bBAY-\d{2}-[A-Z]\b", text, re.I)
    return m.group(0).upper() if m else None


def complete(*, task: str, messages: list[dict[str, str]], json_mode: bool) -> str:
    user = _last_user(messages)

    if task == "clarify":
        needs = _study_id(user) is None and _compound(user) is None and _species(user) is None
        payload = {
            "needs_clarification": bool(needs),
            "question": (
                "Which compound, species, or study ID should I focus on?"
                if needs else ""
            ),
            "recommended_sources": ["studies (SQL++)", "documents (RAG)"],
        }
        return json.dumps(payload)

    if task == "route":
        # decide which tools the researcher should use
        structured = bool(re.search(r"how many|count|average|list|give me \d+|noael|lowest|per species", user, re.I))
        unstructured = bool(re.search(r"observ|finding|sign|effect|why|summar|reversible|histopath", user, re.I)) or _study_id(user)
        if not structured and not unstructured:
            unstructured = True
        return json.dumps({
            "use_rag": bool(unstructured),
            "use_sql": bool(structured),
            "plan": "Retrieve evidence then synthesize a grounded answer with citations.",
        })

    if task == "think_plan":
        return json.dumps({
            "reasoning": "The query references specific findings; route to hybrid RAG "
                         "with a study-id metadata filter, then validate sufficiency.",
            "next_action": "research",
        })

    if task == "keyword_extraction":
        return json.dumps({"keywords": _keywords(user)})

    if task == "metadata_filter":
        f = {}
        sid = _study_id(user)
        sp = _species(user)
        cp = _compound(user)
        if sid:
            f["study_id"] = sid
        if sp:
            f["species"] = sp
        if cp:
            f["compound"] = cp
        return json.dumps({"filter": f})

    if task == "query_expansion":
        base = user.strip().rstrip("?")
        variants = [
            base,
            base.replace("clinical findings", "clinical signs"),
            base.replace("observed", "recorded"),
            "Symptoms and observations reported: " + ", ".join(_keywords(user)[:5]),
            "Adverse effects noted in the report regarding " + ", ".join(_keywords(user)[:4]),
        ]
        # unique, capped
        out, seen = [], set()
        for v in variants:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return json.dumps({"expansions": out[:5]})

    if task == "rerank":
        # messages[-1] carries the candidates as JSON in content after a marker
        m = re.search(r"CANDIDATES:\s*(\[.*\])", user, re.S)
        n = len(json.loads(m.group(1))) if m else 0
        return json.dumps({"order": list(range(n))})

    if task in ("sql_generation", "sql_fix"):
        # only look at the trailing "QUESTION: ..." so few-shot examples in the
        # prompt don't leak entities into the mock's parsing.
        m = re.search(r"QUESTION:\s*(.+)", user, re.S)
        question = m.group(1).strip() if m else user
        return json.dumps({"sql": _mock_sql(question)})

    if task == "reflection":
        # data reflection: is the retrieved context sufficient?
        has_context = "CONTEXT:" in user and len(user) > 200
        return json.dumps({
            "sufficient": bool(has_context),
            "missing": [] if has_context else ["no evidence retrieved"],
            "followup_queries": [],
        })

    if task == "writer" or task == "rag_synthesis":
        return _mock_answer(user)

    if task == "ner_extraction":
        return json.dumps(_mock_ner(user))

    if task == "eval_judge":
        # crude semantic overlap score
        return json.dumps({"score": 0.8, "rationale": "mock heuristic judgement"})

    # generic fallback
    return json.dumps({"result": "ok"}) if json_mode else "OK (mock)"


def _mock_sql(user: str) -> str:
    sp = _species(user)
    cp = _compound(user)
    if re.search(r"how many|count|per species", user, re.I):
        return ("SELECT species, COUNT(*) AS study_count FROM studies "
                "WHERE glp_compliant = true GROUP BY species ORDER BY study_count DESC LIMIT 50")
    if re.search(r"lowest noael", user, re.I) and cp:
        return (f'SELECT study_id, study_title, species, noael_mg_kg_day FROM studies '
                f'WHERE compound = "{cp}" AND noael_mg_kg_day IS NOT MISSING '
                f'ORDER BY noael_mg_kg_day ASC LIMIT 1')
    cond = []
    if sp:
        cond.append(f'species = "{sp}"')
    if cp:
        cond.append(f'compound = "{cp}"')
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    return ("SELECT study_id, study_title, compound, species, route, study_type, year "
            f"FROM studies{where} LIMIT 50")


def _mock_answer(user: str) -> str:
    """Produce a grounded-looking answer with inline [chunk_id] citations if the
    context block contains chunk markers."""
    ctx = ""
    m = re.search(r"CONTEXT:\s*(.*)", user, re.S)
    if m:
        ctx = m.group(1)
    cites = re.findall(r"\[cite:([^\]]+)\]", ctx)
    if "piloerection" in ctx.lower():
        c = cites[0] if cites else "T123456-2::sec3.2::p044::c0"
        return (
            f"Yes — all four signs were observed at 150 mg/kg/day in study T123456-2. "
            f"Piloerection, ataxia, eyes partially closed, and loose faeces were reported, "
            f"appearing transiently from week 4 onward and absent at 25 and 75 mg/kg/day [cite:{c}]."
        )
    if ctx.strip():
        c = cites[0] if cites else "unknown"
        first = ctx.strip().split("\n", 1)[0]
        # strip an existing [cite:..] marker from the echoed context line
        first = re.sub(r"\[cite:[^\]]+\]\s*", "", first)[:400]
        return f"Based on the retrieved study reports: {first} [cite:{c}]"
    return "I could not find sufficient evidence in the indexed study reports to answer that."


def _mock_ner(user: str) -> dict[str, Any]:
    fields = {}
    sid = _study_id(user)
    sp = _species(user)
    cp = _compound(user)
    if sid:
        fields["study_id"] = {"value": sid, "confidence": 0.98}
    if cp:
        fields["compound"] = {"value": cp, "confidence": 0.93}
    if sp:
        fields["species"] = {"value": sp, "confidence": 0.88}
    if re.search(r"gavage", user, re.I):
        fields["route"] = {"value": "Oral gavage", "confidence": 0.6}
    return {"entities": fields}
