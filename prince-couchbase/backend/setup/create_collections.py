"""Create the bucket scope, all collections, and primary/secondary GSI indexes.

Idempotent — safe to re-run. On Capella the bucket itself is usually created in
the UI; set CB_BUCKET to its name. This script creates the scope + collections
inside it and the SQL++ (GSI) indexes needed by the Text-to-SQL++ path.

    python -m backend.setup.create_collections
"""
from __future__ import annotations

import sys
import time

from couchbase.exceptions import (
    ScopeAlreadyExistsException,
    CollectionAlreadyExistsException,
)

# Allow running as a script from repo root
sys.path.insert(0, ".")
from backend.app.config import settings                       # noqa: E402
from backend.app.couchbase_client import get_cluster, cluster_query  # noqa: E402

COLLECTIONS = [
    settings.coll_studies,
    settings.coll_documents,
    settings.coll_sql_examples,
    settings.coll_checkpoints,
    settings.coll_sessions,
    settings.coll_logs,
    settings.coll_citations,
    settings.coll_ner_queue,
]


def main() -> None:
    cluster = get_cluster()
    bucket = cluster.bucket(settings.cb_bucket)
    cm = bucket.collections()

    # 1. Scope
    try:
        cm.create_scope(settings.cb_scope)
        print(f"[+] created scope {settings.cb_scope}")
    except ScopeAlreadyExistsException:
        print(f"[=] scope {settings.cb_scope} exists")

    # 2. Collections
    for coll in COLLECTIONS:
        try:
            cm.create_collection(settings.cb_scope, coll)
            print(f"[+] created collection {coll}")
        except CollectionAlreadyExistsException:
            print(f"[=] collection {coll} exists")

    time.sleep(3)  # let KV settle before building indexes

    # 3. GSI indexes for SQL++ (Text-to-SQL++ over `studies`, plus admin queries)
    ks = settings.keyspace  # helper -> `bucket`.`scope`.`coll`
    ddl = [
        f"CREATE PRIMARY INDEX IF NOT EXISTS ON {ks(settings.coll_studies)}",
        f"CREATE PRIMARY INDEX IF NOT EXISTS ON {ks(settings.coll_documents)}",
        f"CREATE PRIMARY INDEX IF NOT EXISTS ON {ks(settings.coll_sql_examples)}",
        f"CREATE PRIMARY INDEX IF NOT EXISTS ON {ks(settings.coll_logs)}",
        f"CREATE PRIMARY INDEX IF NOT EXISTS ON {ks(settings.coll_ner_queue)}",
        # Targeted secondary indexes speed up the common filters
        f"CREATE INDEX idx_studies_species IF NOT EXISTS ON {ks(settings.coll_studies)}(species)",
        f"CREATE INDEX idx_studies_compound IF NOT EXISTS ON {ks(settings.coll_studies)}(compound)",
        f"CREATE INDEX idx_studies_route IF NOT EXISTS ON {ks(settings.coll_studies)}(route)",
        f"CREATE INDEX idx_studies_year IF NOT EXISTS ON {ks(settings.coll_studies)}(year)",
        f"CREATE INDEX idx_docs_study IF NOT EXISTS ON {ks(settings.coll_documents)}(study_id)",
    ]
    for stmt in ddl:
        try:
            cluster_query(stmt)
            print(f"[+] {stmt}")
        except Exception as exc:  # noqa: BLE001
            print(f"[!] {stmt}  -> {exc}")

    print("\nDone. Next: create FTS indexes (setup/create_indexes.py), then seed_data.py")


if __name__ == "__main__":
    main()
