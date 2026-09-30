"""Text-to-SQL++ for structured data.

The article's "Text-to-SQL" becomes Text-to-SQL++ because Couchbase's query
language is SQL++ (N1QL) over JSON. Pipeline:
  1. schema understanding   — inject only the relevant slice of the studies schema
  2. dynamic few-shot       — nearest NL->SQL++ exemplars from `sql_examples` (vector)
  3. generation + validation — SELECT-only guardrail, force study_id/study_title, LIMIT 50
  4. execute against Couchbase SQL++
  5. self-correct on error, up to SQL_MAX_RETRIES
"""
from __future__ import annotations

import re
from typing import Any

from ..config import settings
from ..llm import llm
from ..embeddings import embedder
from ..couchbase_client import query
from ..search import vector_similarity
from .. import prompts

# The structured schema exposed to the model (the "Athena table" definition).
STUDIES_SCHEMA = """collection `studies` (one document per preclinical study):
  study_id           string   e.g. "T123456-2"   (ALWAYS project)
  study_title        string                        (ALWAYS project)
  compound           string   e.g. "BAY-45-A"
  species            string   one of RAT, DOG, MONKEY, MOUSE, IN_VITRO
  strain             string
  route              string   e.g. "Oral gavage", "Dietary admixture", "Inhalation (nose-only)"
  study_type         string   e.g. "Repeat-dose toxicity", "Chronic toxicity",
                              "Carcinogenicity", "Genotoxicity", "Developmental toxicity",
                              "Acute toxicity", "Dose range-finding"
  duration_weeks     number
  glp_compliant      boolean
  noael_mg_kg_day    number   (may be MISSING for in-vitro / inhalation studies)
  loael_mg_kg_day    number
  sex                array of string  ["M","F"]
  n_animals          number
  dose_groups_mg_kg_day array of number
  year               number
  report_status      string   "Final" | "Draft"
  key_findings       array of string"""

_FORBIDDEN = re.compile(r"\b(UPDATE|DELETE|INSERT|UPSERT|MERGE|DROP|CREATE|ALTER|GRANT|REVOKE)\b", re.I)
_LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.I)


class SQLValidationError(ValueError):
    pass


def retrieve_examples(question: str, k: int = 4) -> list[dict[str, str]]:
    vec = embedder.embed_one(question)
    ex = vector_similarity(vec, settings.coll_sql_examples, k=k)
    return [{"question": e["question"], "sql": e["sql"]} for e in ex]


def _format_examples(examples: list[dict[str, str]]) -> str:
    return "\n".join(f'Q: {e["question"]}\nSQL: {e["sql"]}' for e in examples)


def validate(sql: str) -> str:
    stmt = sql.strip().rstrip(";")
    if not re.match(r"^\s*SELECT\b", stmt, re.I):
        raise SQLValidationError("Only SELECT queries are permitted.")
    if _FORBIDDEN.search(stmt):
        raise SQLValidationError("Mutating/DDL keywords are not permitted.")
    # force essential columns
    low = stmt.lower()
    if "select *" not in low:
        if "study_id" not in low:
            stmt = re.sub(r"^\s*SELECT\b", "SELECT study_id,", stmt, count=1, flags=re.I)
        if "study_title" not in low:
            stmt = re.sub(r"^\s*SELECT\b", "SELECT study_title,", stmt, count=1, flags=re.I)
    # enforce row cap
    if not _LIMIT_RE.search(stmt):
        stmt = f"{stmt} LIMIT {settings.sql_max_rows}"
    else:
        def _cap(m):
            n = int(re.search(r"\d+", m.group()).group())
            return f"LIMIT {min(n, settings.sql_max_rows)}"
        stmt = _LIMIT_RE.sub(_cap, stmt)
    return stmt


def generate(question: str, examples: list[dict[str, str]]) -> str:
    out = llm.json(
        [{"role": "user", "content": prompts.SQL_GENERATION.format(
            schema=STUDIES_SCHEMA,
            examples=_format_examples(examples),
            max_rows=settings.sql_max_rows,
            question=question,
        )}],
        task="sql_generation",
    )
    return out["sql"]


def fix(question: str, sql: str, error: str) -> str:
    out = llm.json(
        [{"role": "user", "content": prompts.SQL_FIX.format(
            sql=sql, error=error, question=question, max_rows=settings.sql_max_rows)}],
        task="sql_fix",
    )
    return out["sql"]


def run(question: str, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    steps = steps if steps is not None else []

    examples = retrieve_examples(question)
    steps.append({"step": "sql_fewshot", "examples": [e["question"] for e in examples]})

    sql = generate(question, examples)
    last_error = None
    for attempt in range(1, settings.sql_max_retries + 1):
        try:
            safe = validate(sql)
            steps.append({"step": "sql_generation", "attempt": attempt, "sql": safe})
            rows = query(safe)
            steps.append({"step": "sql_execute", "attempt": attempt, "n_rows": len(rows)})
            return {"sql": safe, "rows": rows, "steps": steps, "error": None}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            steps.append({"step": "sql_error", "attempt": attempt, "error": last_error})
            if attempt < settings.sql_max_retries:
                sql = fix(question, sql, last_error)
    return {"sql": sql, "rows": [], "steps": steps, "error": last_error}
