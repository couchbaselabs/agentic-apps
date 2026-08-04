"""Create the two Full-Text Search indexes (scope-level):

  * prince_documents_vec  — vector field `embedding` + text field `text` (hybrid RAG)
  * prince_documents_text — pure BM25 text index (keyword search)

Uses the scope-level Search Index Manager, which is how Couchbase 7.6+/Capella
exposes collection-aware FTS indexes. The JSON definitions live next to this file.

    python -m backend.setup.create_indexes

NOTE: the JSON files pin dims=1536 and sourceName="prince". If you changed
EMBED_DIM or CB_BUCKET, this script patches those fields before upserting.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from backend.app.config import settings                # noqa: E402
from backend.app.couchbase_client import get_cluster   # noqa: E402

from couchbase.management.search import SearchIndex     # noqa: E402

HERE = Path(__file__).parent


def _load(path: Path) -> dict:
    idx = json.loads(path.read_text())
    # keep JSON in sync with .env
    idx["sourceName"] = settings.cb_bucket
    # patch collection type key + vector dims
    types = idx["params"]["mapping"]["types"]
    new_types = {}
    for _k, v in types.items():
        new_types[f"{settings.cb_scope}.{settings.coll_documents}"] = v
    idx["params"]["mapping"]["types"] = new_types
    # vector dims
    for tv in new_types.values():
        emb = tv.get("properties", {}).get("embedding")
        if emb:
            for f in emb["fields"]:
                if f.get("type") == "vector":
                    f["dims"] = settings.embed_dim
    return idx


def main() -> None:
    cluster = get_cluster()
    scope = cluster.bucket(settings.cb_bucket).scope(settings.cb_scope)
    # Scope-level search index manager (7.6+/Capella). Falls back to cluster mgr.
    try:
        mgr = scope.search_indexes()
        scoped = True
    except Exception:  # noqa: BLE001
        mgr = cluster.search_indexes()
        scoped = False

    for fname, cfg_name in [
        ("fts_vector_index.json", settings.cb_fts_vector_index),
        ("fts_text_index.json", settings.cb_fts_text_index),
    ]:
        raw = _load(HERE / fname)
        raw["name"] = cfg_name
        index = SearchIndex.from_json(raw)
        try:
            mgr.upsert_index(index)
            where = "scope" if scoped else "cluster"
            print(f"[+] upserted FTS index '{cfg_name}' ({where}-level)")
        except Exception as exc:  # noqa: BLE001
            print(f"[!] failed to upsert '{cfg_name}': {exc}")
            print("    You can also import the JSON directly in the Capella UI:")
            print(f"    Search -> Add Index -> Import from File -> {fname}")

    print("\nIndexes may take a minute to build. Check Search tab in Capella.")


if __name__ == "__main__":
    main()
