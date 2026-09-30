# PRINCE-on-Couchbase — Architecture

This project is a faithful, deployable recreation of **PRINCE** (Preclinical
Information Center), the agentic RAG + Text-to-SQL system described in Martin
Fowler's article *"Building Reliable Agentic AI Systems"* (Bayer × Thoughtworks).

The one deliberate change: **every database, search, and state-persistence need
is served by Couchbase.** Nothing else (no Postgres, no DynamoDB, no Athena, no
S3, no OpenSearch) is required. Couchbase is a multi-model engine — it does
key-value, SQL (SQL++/N1QL over JSON), full-text search, and vector search in one
cluster — which is exactly the set of capabilities PRINCE assembled from five AWS
services.

## 1. Service mapping — what replaces what

| PRINCE component (article)                         | Role                                   | Couchbase equivalent here                                            |
|----------------------------------------------------|----------------------------------------|---------------------------------------------------------------------|
| **PostgreSQL** — LangGraph checkpointer            | Durable agent/graph state              | Collection `checkpoints` + a custom `CouchbaseSaver` (BaseCheckpointSaver) |
| **DynamoDB** — app state, logs, steps, citations   | Fast KV app data                       | Collections `sessions`, `logs`, `citations` (KV get/upsert)         |
| **Amazon Athena** — structured/curated metadata    | SQL analytics over structured data     | Collection `studies`, queried with **SQL++** (Text-to-SQL++)         |
| **Amazon S3** — data lake of study report PDFs      | Unstructured document store            | Collection `documents` (normalized JSON chunks; raw text in KV)      |
| **Amazon OpenSearch** — vector store + hybrid search | Semantic + keyword retrieval          | Couchbase **FTS Vector index** (`..._vec`) + **FTS text index** (`..._text`) |
| **"Semantic layer"** — few-shot Text-to-SQL examples | In-context SQL exemplars              | Collection `sql_examples`, retrieved by **vector similarity**        |
| **CloudWatch / Langfuse / RAGAS**                   | Observability + eval                   | Structured logs in `logs` + optional Langfuse + `app/eval/` harness  |
| **Unified OpenAI-compatible LLM endpoint**          | Multi-provider model access            | `app/llm.py` — OpenAI-compatible client + provider fallback + mock   |
| **LangGraph harness**                               | Control layer / workflow               | `app/graph.py` — same LangGraph state machine                        |
| **React conversational UI**                         | Front end with citations              | `frontend/` (Vite + React)                                          |

Because a single Couchbase cluster covers KV + SQL + FTS + Vector, the entire
"data flow architecture" of the article collapses from five managed services into
**one bucket with a few collections and two search indexes**.

## 2. Physical data model (one bucket, one scope, many collections)

```
bucket: prince
└── scope: main
    ├── studies        # STRUCTURED metadata (one doc per study)   -> SQL++ / Text-to-SQL++
    ├── documents      # UNSTRUCTURED report chunks + embeddings   -> FTS text + FTS vector (hybrid RAG)
    ├── sql_examples   # few-shot NL->SQL++ pairs + embeddings     -> vector similarity ("semantic layer")
    ├── checkpoints    # LangGraph durable graph state             -> KV (CouchbaseSaver)
    ├── sessions       # per-conversation app state                -> KV
    ├── logs           # intermediate steps / traces               -> KV + SQL++ for analytics
    ├── citations      # granular per-sentence citations           -> KV
    └── ner_queue      # low-confidence NER fields for human review -> KV + SQL++
```

### `studies` document (structured — the "Athena" table)
```json
{
  "type": "study",
  "study_id": "T123456-2",
  "study_title": "13-Week Oral Toxicity Study of Compound BAY-45-A in Wistar Rats",
  "compound": "BAY-45-A",
  "species": "RAT",
  "strain": "Wistar",
  "route": "Oral gavage",
  "study_type": "Repeat-dose toxicity",
  "duration_weeks": 13,
  "glp_compliant": true,
  "noael_mg_kg_day": 25.0,
  "sex": ["M", "F"],
  "n_animals": 80,
  "dose_groups_mg_kg_day": [0, 25, 75, 150],
  "year": 2016,
  "report_status": "Final",
  "key_findings": ["hepatocellular hypertrophy at 150 mg/kg/day", "..."]
}
```

### `documents` chunk (unstructured — the "S3 + OpenSearch" record)
```json
{
  "type": "chunk",
  "chunk_id": "T123456-2::sec3.2::p044::c0",
  "study_id": "T123456-2",
  "compound": "BAY-45-A",
  "species": "RAT",
  "route": "Oral gavage",
  "page": 44,
  "parent_section": "3.2 Clinical Signs",
  "text": "During the treatment period, piloerection and ataxia were observed ...",
  "embedding": [0.0123, -0.0456, ...]   // EMBED_DIM floats
}
```

## 3. The agentic workflow (harness engineering)

`app/graph.py` builds the exact LangGraph pipeline from the article. Each node
gets its own **context** (context engineering) and the graph is the **harness**
that decides who runs, when to pause, and how to recover.

```
        ┌─────────────┐
 user → │  CLARIFY    │  disambiguate intent, recommend data sources, fail-fast
        └──────┬──────┘
               ▼
        ┌─────────────┐
        │ THINK/PLAN  │  process reflection (Anthropic "think" tool) — pick tools
        └──────┬──────┘
               ▼
        ┌─────────────┐   RAG (unstructured)         Text-to-SQL++ (structured)
        │ RESEARCHER  │──► hybrid retriever  ────┐   ──► schema inject + few-shot
        └──────┬──────┘   keyword+filter+expand  │       SELECT-only + retry x3
               │          weighted vec/kw + rerank│       cap 50 rows (SQL++/Couchbase)
               ▼                                  ▼
        ┌─────────────┐   evidence sufficient? ── no ─► back to THINK/PLAN (follow-ups)
        │ REFLECTION  │   (data reflection)
        └──────┬──────┘   yes
               ▼
        ┌─────────────┐  grounded answer, per-sentence citations, formatting,
        │  WRITER     │  internal review loop for long/regulatory drafts
        └──────┬──────┘
               ▼   response + citations + intermediate steps  → React UI
```

State is persisted at every node via `CouchbaseSaver` (collection `checkpoints`),
so a failed run can be resumed from the failed node — the article's
"user-initiated retry that skips previously successful steps."

## 4. Hybrid Retriever (RAG for unstructured data)

Query: *"Were any of the following clinical findings observed in study T123456-2:
piloerection, ataxia, eyes partially closed, and loose faeces?"*

1. **Keyword extraction** (fast LLM) → `["piloerection","ataxia","eyes partially closed","loose faeces"]`
2. **Metadata filter generation** (fast LLM, few-shot) → `eq(study_id, "T123456-2")`
   → compiled to a Couchbase FTS `conjuncts` filter, pre-narrowing millions→hundreds.
3. **Query expansion** (fast LLM, n=5) → semantically varied paraphrases.
4. **Parallel hybrid search** — for each expansion, one Couchbase Search request that
   combines a **vector query** (kNN on `embedding`) and a **text query** (BM25 on `text`)
   under a single `conjuncts`/`disjuncts` FTS query. Scores blended
   `0.7*semantic + 0.3*keyword`.
5. **Aggregate** unique chunks by best weighted score (k≈20).
6. **Rerank** with a cross-encoder (bge-reranker-large if available; otherwise an
   LLM-scored fallback) → top k=7.
7. **Synthesize** with the strong model → grounded answer + citations.

All of steps 4–6 are **native Couchbase Search** — no external vector DB.

## 5. Text-to-SQL++ (structured data)

The article's "Text-to-SQL" becomes **Text-to-SQL++** because Couchbase's query
language is SQL++ (N1QL) over JSON. Same pipeline:

1. Intent recognition → which fields/filters are needed.
2. **Schema understanding** — only the relevant slice of the `studies` schema is
   injected (see `app/agents/text_to_sql.py::STUDIES_SCHEMA`).
3. **Dynamic few-shot** — nearest NL→SQL++ exemplars pulled from `sql_examples`
   by vector similarity.
4. **Generation + validation** — strong model writes SQL++, validator enforces
   **SELECT-only** (rejects UPDATE/DELETE/INSERT/MERGE/DROP), always includes
   `study_id` & `study_title`, and injects `LIMIT 50`.
5. **Execute** against Couchbase SQL++.
6. **Self-correct** — on error, feed the error + query back to the model, up to 3×.

## 6. Reliability features (all preserved)

- **Durable state / resume-from-failure** — `CouchbaseSaver`.
- **Automatic retries** — `tenacity` around LLM + query calls.
- **LLM provider fallback** — secondary OpenAI-compatible endpoint.
- **SELECT-only guardrail** + row cap for Text-to-SQL++.
- **Granular citations** — every sentence links to `chunk_id`, page, exact quote.
- **Transparency** — intermediate steps streamed and stored in `logs`.
- **NER data-quality** — confidence-scored field extraction; high-confidence
  auto-updates `studies`, low-confidence goes to `ner_queue` for human review.
- **Evaluation harness** — faithfulness, answer relevancy, context relevancy,
  answer accuracy, semantic similarity; dataset + live-traffic modes.

## 7. Why Couchbase fits PRINCE unusually well

PRINCE needed *structured filtering/aggregation* **and** *semantic + keyword
retrieval* **and** *durable low-latency state*, and originally stitched five AWS
services together to get them. Couchbase provides all three natively over the same
JSON documents, so a chunk's rich metadata (study_id, species, route, page,
section) is both a **SQL++ predicate** and an **FTS filter** without any ETL between
systems — the metadata filter that pre-narrows the vector search is literally the
same field the Text-to-SQL++ path aggregates on.
