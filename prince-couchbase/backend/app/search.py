"""Couchbase hybrid search — the OpenSearch replacement.

Provides:
  * hybrid_search(): weighted vector (kNN) + keyword (BM25) over the `documents`
    collection, pre-filtered by metadata (study_id/species/compound/route).
  * vector_similarity(): pure kNN, used by the Text-to-SQL++ few-shot retriever.

If the FTS indexes aren't built yet (or the Search service is unreachable), we
transparently fall back to a SQL++ brute-force cosine scan so the pipeline still
works during setup. In production the FTS path is what runs.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from .config import settings
from .couchbase_client import get_scope, query, kv_get

# Couchbase SDK search primitives
try:
    from couchbase.search import (
        SearchRequest,
        MatchQuery,
        TermQuery,
        ConjunctionQuery,
        DisjunctionQuery,
        SearchOptions,
    )
    from couchbase.vector_search import VectorSearch, VectorQuery
    _SEARCH_OK = True
except Exception:  # noqa: BLE001
    _SEARCH_OK = False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# Primary path: native Couchbase FTS + Vector Search
# ---------------------------------------------------------------------------
def _fts_hybrid(
    index_name: str,
    query_text: str,
    query_vector: list[float],
    filters: dict[str, str],
    k: int,
) -> list[dict[str, Any]]:
    scope = get_scope()

    # keyword side: match query on `text`, boosted by keyword weight
    kw = MatchQuery(query_text, field="text", boost=settings.rag_keyword_weight)

    # metadata pre-filter: conjunction of exact-term queries
    filter_queries = [TermQuery(v, field=key) for key, v in filters.items() if v]

    if filter_queries:
        fts_query = ConjunctionQuery(kw, *filter_queries)
    else:
        fts_query = kw

    # vector side: kNN on `embedding`, boosted by semantic weight
    vq = VectorQuery(
        "embedding",
        query_vector,
        num_candidates=max(k * 3, settings.rag_initial_k),
        boost=settings.rag_semantic_weight,
    )
    vsearch = VectorSearch.from_vector_query(vq)

    request = SearchRequest.create(fts_query).with_vector_search(vsearch)
    opts = SearchOptions(limit=k, fields=["study_id", "page", "parent_section", "compound", "species", "route"])
    res = scope.search(index_name, request, opts)

    rows: list[dict[str, Any]] = []
    for row in res.rows():
        doc = kv_get(settings.coll_documents, row.id) or {}
        rows.append({
            "chunk_id": row.id,
            "score": row.score,
            "text": doc.get("text", ""),
            "study_id": doc.get("study_id", ""),
            "page": doc.get("page"),
            "parent_section": doc.get("parent_section", ""),
            "compound": doc.get("compound", ""),
            "species": doc.get("species", ""),
            "route": doc.get("route", ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Fallback path: SQL++ brute-force cosine (used until FTS indexes are live)
# ---------------------------------------------------------------------------
def _sqlpp_fallback(
    query_text: str,
    query_vector: list[float],
    filters: dict[str, str],
    k: int,
) -> list[dict[str, Any]]:
    where = ["type = \"chunk\""]
    params: dict[str, Any] = {}
    for key, val in filters.items():
        if val:
            where.append(f"{key} = ${key}")
            params[key] = val
    clause = " AND ".join(where)
    docs = query(
        f"SELECT chunk_id, study_id, page, parent_section, compound, species, route, "
        f"text, embedding FROM {settings.coll_documents} WHERE {clause} LIMIT 2000",
        params or None,
    )
    kw_terms = [t for t in query_text.lower().split() if len(t) > 3]
    scored = []
    for d in docs:
        sem = _cosine(query_vector, d.get("embedding", []))
        text_l = d.get("text", "").lower()
        kw = sum(text_l.count(t) for t in kw_terms)
        kw_norm = min(kw / 5.0, 1.0)
        score = settings.rag_semantic_weight * sem + settings.rag_keyword_weight * kw_norm
        d.pop("embedding", None)
        d["score"] = score
        scored.append(d)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


def hybrid_search(
    query_text: str,
    query_vector: list[float],
    filters: Optional[dict[str, str]] = None,
    k: Optional[int] = None,
) -> list[dict[str, Any]]:
    filters = {kk: vv for kk, vv in (filters or {}).items() if vv}
    k = k or settings.rag_initial_k
    if _SEARCH_OK:
        try:
            rows = _fts_hybrid(settings.cb_fts_vector_index, query_text, query_vector, filters, k)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001
            # FTS not ready / transient — degrade gracefully
            print(f"[search] FTS path unavailable ({exc}); using SQL++ fallback")
    return _sqlpp_fallback(query_text, query_vector, filters, k)


def vector_similarity(query_vector: list[float], collection: str, k: int = 3) -> list[dict[str, Any]]:
    """Pure vector similarity over an arbitrary collection (used for the
    Text-to-SQL++ few-shot 'semantic layer'). SQL++ cosine scan — the example
    set is small, so this is exact and cheap."""
    docs = query(
        f"SELECT question, sql, embedding FROM {collection} LIMIT 500"
    )
    scored = []
    for d in docs:
        s = _cosine(query_vector, d.get("embedding", []))
        d.pop("embedding", None)
        d["score"] = s
        scored.append(d)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]
