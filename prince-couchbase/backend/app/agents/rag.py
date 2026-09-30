"""RAG for unstructured data — the full PRINCE hybrid retriever.

Pipeline (all Couchbase-native for retrieval):
  1. keyword extraction        (fast LLM)
  2. metadata filter generation (fast LLM, few-shot) -> Couchbase FTS pre-filter
  3. query expansion n=5       (fast LLM)
  4. parallel hybrid search    (Couchbase FTS text + vector, weighted 0.7/0.3)
  5. aggregate unique chunks   (best weighted score across expansions)
  6. rerank -> top k=7         (cross-encoder if available, else LLM reranker)
  7. synthesize + citations    (strong LLM)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..config import settings
from ..llm import llm
from ..embeddings import embedder
from ..search import hybrid_search
from .. import prompts

# Optional cross-encoder reranker (bge-reranker-large, as in the article).
_CROSS = None
def _cross_encoder():
    global _CROSS
    if _CROSS is None:
        try:
            from sentence_transformers import CrossEncoder
            _CROSS = CrossEncoder("BAAI/bge-reranker-large")
        except Exception:  # noqa: BLE001
            _CROSS = False  # unavailable -> LLM reranker fallback
    return _CROSS


def extract_keywords(question: str) -> list[str]:
    out = llm.json(
        [{"role": "user", "content": prompts.KEYWORD_EXTRACTION.format(question=question)}],
        fast=True, task="keyword_extraction",
    )
    return out.get("keywords", [])


def generate_metadata_filter(question: str) -> dict[str, str]:
    out = llm.json(
        [{"role": "user", "content": prompts.METADATA_FILTER.format(question=question)}],
        fast=True, task="metadata_filter",
    )
    return {k: v for k, v in (out.get("filter", {}) or {}).items() if v}


def expand_query(question: str, n: int) -> list[str]:
    out = llm.json(
        [{"role": "user", "content": prompts.QUERY_EXPANSION.format(question=question, n=n)}],
        fast=True, task="query_expansion",
    )
    exps = out.get("expansions", [])
    if question not in exps:
        exps = [question] + exps
    return exps[:n]


def _search_one(qtext: str, filters: dict[str, str], k: int) -> list[dict[str, Any]]:
    vec = embedder.embed_one(qtext)
    return hybrid_search(qtext, vec, filters, k)


def aggregate(results: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for group in results:
        for row in group:
            cid = row["chunk_id"]
            if cid not in best or row["score"] > best[cid]["score"]:
                best[cid] = row
    return sorted(best.values(), key=lambda r: r["score"], reverse=True)


def rerank(question: str, candidates: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    if not candidates:
        return []
    ce = _cross_encoder()
    if ce:
        pairs = [(question, c["text"]) for c in candidates]
        scores = ce.predict(pairs)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)[:k]
    # LLM reranker fallback
    import json as _json
    slim = [{"i": i, "text": c["text"][:400]} for i, c in enumerate(candidates)]
    out = llm.json(
        [{"role": "user", "content": prompts.RERANK.format(
            question=question, candidates=_json.dumps(slim))}],
        fast=True, task="rerank",
    )
    order = out.get("order", list(range(len(candidates))))
    ordered = [candidates[i] for i in order if 0 <= i < len(candidates)]
    return ordered[:k] if ordered else candidates[:k]


def build_context(chunks: list[dict[str, Any]]) -> str:
    lines = []
    for c in chunks:
        marker = f"[cite:{c['chunk_id']}]"
        lines.append(
            f"{marker} (study {c['study_id']}, p.{c.get('page')}, {c.get('parent_section','')}):\n"
            f"{c['text']}"
        )
    return "\n\n".join(lines)


def synthesize(question: str, chunks: list[dict[str, Any]]) -> str:
    context = build_context(chunks)
    return llm.complete(
        [{"role": "user", "content": prompts.RAG_SYNTHESIS.format(question=question, context=context)}],
        task="rag_synthesis",
    )


def run(question: str, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Execute the whole hybrid RAG. Returns retrieved chunks + a draft answer +
    the intermediate steps (for transparency, stored in `logs`)."""
    steps = steps if steps is not None else []

    keywords = extract_keywords(question)
    steps.append({"step": "keyword_extraction", "keywords": keywords})

    filters = generate_metadata_filter(question)
    steps.append({"step": "metadata_filter", "filter": filters})

    expansions = expand_query(question, settings.rag_expansions)
    steps.append({"step": "query_expansion", "expansions": expansions})

    # parallel hybrid search across expansions
    with ThreadPoolExecutor(max_workers=min(5, len(expansions))) as pool:
        results = list(pool.map(
            lambda q: _search_one(q, filters, max(4, settings.rag_initial_k // len(expansions) + 2)),
            expansions,
        ))
    candidates = aggregate(results)
    steps.append({"step": "hybrid_search", "n_candidates": len(candidates),
                  "weights": {"semantic": settings.rag_semantic_weight,
                              "keyword": settings.rag_keyword_weight}})

    top = rerank(question, candidates, settings.rag_final_k)
    steps.append({"step": "rerank", "n_final": len(top),
                  "chunk_ids": [c["chunk_id"] for c in top]})

    answer = synthesize(question, top) if top else \
        "No relevant evidence was found in the indexed study reports."

    return {"answer": answer, "chunks": top, "steps": steps, "filters": filters}
