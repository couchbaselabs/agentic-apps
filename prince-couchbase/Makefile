# PRINCE-on-Couchbase — convenience targets.
# Assumes a Python venv is active and `pip install -r requirements.txt` is done.

.PHONY: install setup seed ingest ner api ui demo eval test clean

install:
	pip install -r requirements.txt

# --- Couchbase Capella bootstrap (run once, in order) ---
setup:            ## create scope/collections + GSI indexes
	python -m backend.setup.create_collections

indexes:          ## create FTS text + vector search indexes
	python -m backend.setup.create_indexes

seed:             ## load structured studies + few-shot SQL++ examples
	python -m backend.setup.seed_data

ingest:           ## chunk + embed + index the unstructured reports
	python -m scripts.ingest

ner:              ## run the NER data-quality pass (auto-update vs quarantine)
	python -m scripts.run_ner

bootstrap: setup indexes seed ingest   ## full one-shot bootstrap

# --- run ---
api:              ## start the FastAPI backend on :8000
	uvicorn backend.app.main:app --reload --port 8000

ui:               ## start the React dev server on :5173
	cd frontend && npm install && npm run dev

demo:             ## run the flagship example queries in the terminal
	python -m scripts.demo

eval:             ## dataset evaluation (faithfulness/relevancy/accuracy/...)
	python -m scripts.run_eval

eval-live:        ## live-traffic evaluation over stored sessions
	python -m scripts.run_eval --live

test:             ## unit tests (no cluster needed)
	MOCK_LLM=true pytest -q

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
