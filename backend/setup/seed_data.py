"""Seed structured `studies` and the Text-to-SQL++ `sql_examples` semantic layer.

  * studies       -> loaded verbatim (structured metadata; the "Athena" table)
  * sql_examples  -> each NL question embedded so the Text-to-SQL++ agent can
                     retrieve nearest exemplars by vector similarity.

Run AFTER create_collections.py:
    python -m backend.setup.seed_data
Then run the document ingestion:
    python -m scripts.ingest
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")
from backend.app.config import settings                    # noqa: E402
from backend.app.couchbase_client import kv_upsert         # noqa: E402
from backend.app.embeddings import embedder                # noqa: E402

STUDIES = "backend/data/studies/studies.json"
SQL_EXAMPLES = "backend/data/sql_examples.json"


def seed_studies() -> int:
    studies = json.load(open(STUDIES))
    for s in studies:
        s.setdefault("type", "study")
        kv_upsert(settings.coll_studies, s["study_id"], s)
    return len(studies)


def seed_sql_examples() -> int:
    examples = json.load(open(SQL_EXAMPLES))
    questions = [e["question"] for e in examples]
    vectors = embedder.embed(questions)
    for i, (e, v) in enumerate(zip(examples, vectors)):
        doc = {
            "type": "sql_example",
            "example_id": f"sqlex-{i:03d}",
            "question": e["question"],
            "sql": e["sql"],
            "embedding": v,
        }
        kv_upsert(settings.coll_sql_examples, doc["example_id"], doc)
    return len(examples)


def main() -> None:
    n1 = seed_studies()
    print(f"[+] seeded {n1} studies into `{settings.coll_studies}`")
    n2 = seed_sql_examples()
    print(f"[+] seeded {n2} SQL++ few-shot examples into `{settings.coll_sql_examples}`")
    print("\nNext: python -m scripts.ingest   (index the unstructured reports)")


if __name__ == "__main__":
    main()
