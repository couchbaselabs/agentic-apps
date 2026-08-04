# PRINCE on Couchbase

A faithful, deployable recreation of **PRINCE** (Preclinical Information Center) —
the agentic RAG + Text-to-SQL system Bayer and Thoughtworks describe in Martin
Fowler's article [*Building Reliable Agentic AI Systems*](https://martinfowler.com/articles/reliable-llm-bayer.html) —
**rebuilt so that every database, search, and state need is served by Couchbase.**

PRINCE originally stitched together five AWS services (PostgreSQL, DynamoDB,
Athena, S3, OpenSearch). This project replaces all of them with a single
Couchbase cluster, because Couchbase is multi-model: key-value, SQL (SQL++/N1QL
over JSON), full-text search, and vector search in one engine.

> See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full service-by-service
> mapping and diagrams. This README is the runbook.

## What's inside

- **Five-stage agentic workflow** (LangGraph): clarify → think/plan → researcher →
  reflection → writer, with a **Couchbase-backed checkpointer** for durable state
  and resume-from-failure.
- **Hybrid RAG** over unstructured study reports: keyword extraction → metadata
  filter → 5× query expansion → weighted vector+keyword search (0.7/0.3) →
  cross-encoder rerank → grounded synthesis with **per-sentence citations**. All
  retrieval is **native Couchbase FTS + Vector Search**.
- **Text-to-SQL++**: schema injection, dynamic few-shot from a vector "semantic
  layer", SELECT-only guardrail, 50-row cap, 3× self-correction — generating
  **Couchbase SQL++** over structured study metadata.
- **NER data-quality module**: confidence-scored entity extraction; high-confidence
  fields auto-update `studies`, low-confidence fields quarantine to `ner_queue`.
- **Evaluation harness**: faithfulness, answer relevancy, context relevancy,
  answer accuracy, semantic similarity — dataset + live-traffic modes.
- **React UI**: conversational, with intermediate-steps panel and hover citations
  (study, page, section, exact quote).
- **Pluggable OpenAI-compatible LLM** with provider fallback, plus a **mock mode**
  that runs the entire pipeline deterministically with no API key.
- **Realistic sample data**: 12 preclinical studies (structured) + 4 full study
  reports (unstructured), few-shot SQL++ examples, and a curated eval set.

## Prerequisites

- Python 3.10+
- Node 18+ (for the UI)
- A **Couchbase Capella** cluster (free tier works) with the **Data, Query,
  Index, and Search** services enabled. Create a bucket (default name `prince`)
  and a database user, then allow your IP in Capella's network settings.

## Quick start

```bash
# 1. Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
#   -> fill in CB_CONNECTION_STRING / CB_USERNAME / CB_PASSWORD (Capella)
#   -> fill in LLM_API_KEY + EMBED_API_KEY, OR set MOCK_LLM=true to run offline

# 3. Bootstrap Couchbase (scope, collections, GSI, FTS indexes, data)
make setup       # scope + collections + GSI (SQL++)
make indexes     # FTS text + vector search indexes
make seed        # structured studies + few-shot SQL++ examples
make ingest      # chunk + embed + index the unstructured reports
#   (or: make bootstrap  to do all four)

# 4. Try it
make demo        # runs the flagship example queries end-to-end in the terminal
make api         # FastAPI backend on http://localhost:8000
make ui          # React UI on http://localhost:5173  (separate terminal)
```

### Run with no API key (offline demo)

Set `MOCK_LLM=true` in `.env`. Every agent stage is served by a deterministic
mock and embeddings are hashed, so the full pipeline — graph, Couchbase FTS +
vector + SQL++, citations, eval — runs end-to-end. You still need the Couchbase
cluster (it's the whole point), but no OpenAI/Anthropic key.

> **Note on FTS during setup:** vector/text indexes take a minute to build. Until
> they're live, `search.py` transparently falls back to a SQL++ brute-force cosine
> scan, so `make demo` works immediately after `make seed && make ingest`. Once
> the FTS indexes are ready, the native hybrid-search path takes over automatically.

## The flagship query (from the article)

```
Were any of the following clinical findings observed in study T123456-2:
piloerection, ataxia, eyes partially closed, and loose faeces?
```

This exercises the whole RAG path: the metadata-filter stage narrows to
`study_id = T123456-2`, query expansion generates paraphrases, hybrid search
retrieves the "3.2 Clinical Signs" chunks, rerank picks the best, and the writer
produces a grounded answer citing the exact page and quote.

A structured example that routes to Text-to-SQL++:

```
Give me 50 example studies done on RAT
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | run a question through the agentic graph |
| POST | `/api/chat/{sid}/resume` | resume a failed run from its last checkpoint |
| GET  | `/api/session/{sid}` | fetch stored session (steps + citations) |
| GET  | `/api/studies` | list structured studies (SQL++) |
| GET  | `/api/health` | liveness + config summary |

```bash
curl -s localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"question":"Did BAY-45-A cause any cardiovascular effects in dogs?"}' | jq
```

## Data-quality (NER) and evaluation

```bash
make ner        # extract entities w/ confidence; auto-update vs quarantine
make eval       # dataset evaluation with the RAGAS-style metrics
make eval-live  # live-traffic evaluation over recent sessions
```

## Tests

```bash
make test       # pure-logic units (mock mode, no cluster needed)
```

## Project layout

```
backend/
  app/
    config.py            # all settings (env-driven)
    couchbase_client.py  # cluster, KV, SQL++ helpers
    llm.py               # OpenAI-compatible client + fallback + mock
    embeddings.py        # embeddings (+ deterministic mock)
    mock.py              # deterministic mock LLM (offline pipeline)
    search.py            # Couchbase FTS + Vector hybrid search (+ SQL++ fallback)
    prompts.py           # every agent prompt (context engineering)
    schema.py            # graph state + API models
    checkpointer.py      # CouchbaseSaver (LangGraph durable state)
    graph.py             # the LangGraph state machine (the "harness")
    service.py           # runs the graph + persists app state/logs/citations
    main.py              # FastAPI
    agents/
      rag.py             # hybrid retriever
      text_to_sql.py     # Text-to-SQL++
      nodes.py           # LangGraph node functions (clarify/plan/research/reflect/write)
    ner/extract.py       # NER data-quality
    eval/metrics.py      # evaluation metrics
  setup/                 # create_collections / create_indexes / seed_data + FTS JSON
  data/                  # sample structured + unstructured data, few-shot, eval set
scripts/                 # ingest / demo / run_ner / run_eval
frontend/                # Vite + React UI (chat, steps panel, hover citations)
```

## Deploying to production

Everything is env-driven, so the same code runs against any Couchbase cluster —
Capella or self-managed. For a container deploy, build the backend with the
provided `requirements.txt`, ship `.env` via your secret manager, and run
`uvicorn backend.app.main:app`. Point the React build (`cd frontend && npm run
build`) at the backend URL. Optional Langfuse env vars enable production tracing
exactly as in the article.
