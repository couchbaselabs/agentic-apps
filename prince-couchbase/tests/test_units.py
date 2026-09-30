"""Unit tests for the pure-logic components (no live cluster required).

Run with MOCK_LLM so no API key is needed:
    MOCK_LLM=true pytest -q
"""
import os
os.environ.setdefault("MOCK_LLM", "true")

import sys
sys.path.insert(0, ".")

from backend.app import mock
from backend.app.embeddings import _mock_embed, embedder
from backend.app.agents import text_to_sql
from backend.app.agents.nodes import extract_citations
from scripts import ingest


# ---- mock LLM dispatch ----
def test_mock_keyword_extraction():
    out = mock.complete(task="keyword_extraction", json_mode=True, messages=[
        {"role": "user", "content": "clinical findings in study T123456-2: piloerection, ataxia"}])
    import json
    kws = json.loads(out)["keywords"]
    assert "piloerection" in kws


def test_mock_metadata_filter_study_id():
    import json
    out = json.loads(mock.complete(task="metadata_filter", json_mode=True, messages=[
        {"role": "user", "content": "findings in study T123456-2"}]))
    assert out["filter"]["study_id"] == "T123456-2"


def test_mock_route_sql_vs_rag():
    import json
    sql = json.loads(mock.complete(task="route", json_mode=True, messages=[
        {"role": "user", "content": "give me 50 studies on RAT"}]))
    assert sql["use_sql"] is True
    rag = json.loads(mock.complete(task="route", json_mode=True, messages=[
        {"role": "user", "content": "what findings were observed in T123456-2"}]))
    assert rag["use_rag"] is True


# ---- embeddings ----
def test_mock_embedding_dim_and_norm():
    v = _mock_embed("piloerection ataxia")
    from backend.app.config import settings
    assert len(v) == settings.embed_dim
    import math
    assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6


def test_embedder_batch():
    from backend.app.config import settings
    vs = embedder.embed(["a b c", "d e f"])
    assert len(vs) == 2 and len(vs[0]) == settings.embed_dim


# ---- Text-to-SQL++ validation guardrails ----
def test_validate_rejects_mutations():
    for bad in ["DELETE FROM studies", "UPDATE studies SET x=1", "DROP INDEX foo"]:
        try:
            text_to_sql.validate(bad)
            assert False, "should have rejected " + bad
        except text_to_sql.SQLValidationError:
            pass


def test_validate_forces_columns_and_limit():
    out = text_to_sql.validate('SELECT compound FROM studies WHERE species = "RAT"')
    assert "study_id" in out and "study_title" in out
    assert "LIMIT 50" in out.upper()


def test_validate_caps_limit():
    out = text_to_sql.validate("SELECT study_id, study_title FROM studies LIMIT 5000")
    assert "LIMIT 50" in out.upper()


# ---- citation extraction ----
def test_extract_citations():
    answer = "Signs were seen [cite:T123456-2::sec32::p044::c0] and confirmed [study:T220145-1]."
    state = {"chunks": [{"chunk_id": "T123456-2::sec32::p044::c0", "study_id": "T123456-2",
                         "page": 44, "parent_section": "3.2", "text": "piloerection ..."}]}
    cites = extract_citations(answer, state)
    ids = [c.get("chunk_id") or c.get("study_id") for c in cites]
    assert "T123456-2::sec32::p044::c0" in ids
    assert "T220145-1" in ids


# ---- ingestion chunk parsing ----
def test_parse_txt_markers():
    chunks = ingest.parse_txt("backend/data/documents/T123456-2.txt")
    assert len(chunks) > 3
    pages = {c.page for c in chunks}
    assert 44 in pages
    assert any("piloerection" in c.text.lower() for c in chunks)
    assert all(c.study_id == "T123456-2" for c in chunks)
