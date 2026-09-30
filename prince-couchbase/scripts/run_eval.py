"""Evaluation harness — dataset + live-traffic modes (as in the article).

Dataset mode (default): run the curated QA set (backend/data/eval/qa_dataset.json),
score faithfulness / answer relevancy / context relevancy / answer accuracy /
semantic similarity, and print per-item + aggregate results.

    python -m scripts.run_eval
    python -m scripts.run_eval --live      # score recent live sessions (no references)

Analogous to PRINCE's "dataset evaluations" (on significant changes) and daily
"live traffic evaluations".
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
sys.path.insert(0, ".")

from backend.app import service                       # noqa: E402
from backend.app.config import settings               # noqa: E402
from backend.app.eval import metrics                  # noqa: E402
from backend.app.couchbase_client import query        # noqa: E402
from backend.app.agents.nodes import _context_for_writer  # noqa: E402

DATASET = "backend/data/eval/qa_dataset.json"


def _context_from_result(r: dict) -> str:
    state = {"chunks": [], "rows": r.get("rows", []), "sql": r.get("sql")}
    # reconstruct chunk context from citations' quotes
    for c in r.get("citations", []):
        if c.get("chunk_id"):
            state["chunks"].append({
                "chunk_id": c["chunk_id"], "study_id": c.get("study_id"),
                "page": c.get("page"), "parent_section": c.get("parent_section"),
                "text": c.get("quote") or "",
            })
    return _context_for_writer(state)


def dataset_mode() -> None:
    items = json.load(open(DATASET))
    agg: dict[str, list[float]] = {}
    print(f"Running dataset evaluation on {len(items)} items "
          f"(mock_llm={settings.mock_llm})\n")
    for item in items:
        r = service.run_chat(item["question"])
        context = _context_from_result(r)
        scores = metrics.evaluate_one(item, r["answer"], context, live=False)
        print(f"[{item['id']}] {item['route']:4s} {scores}")
        for k, v in scores.items():
            if isinstance(v, (int, float)):
                agg.setdefault(k, []).append(v)
    print("\n=== AGGREGATE (mean) ===")
    for k, vals in agg.items():
        print(f"  {k:22s} {statistics.mean(vals):.3f}")


def live_mode(limit: int = 20) -> None:
    sessions = query(
        f"SELECT session_id, question, answer FROM {settings.coll_sessions} "
        f"WHERE type = \"session\" LIMIT {int(limit)}"
    )
    print(f"Live-traffic evaluation on {len(sessions)} recent sessions "
          f"(faithfulness + answer relevancy only)\n")
    agg: dict[str, list[float]] = {}
    for s in sessions:
        item = {"question": s["question"], "reference_answer": ""}
        scores = metrics.evaluate_one(item, s.get("answer", ""), "", live=True)
        print(f"[{s['session_id']}] {scores}")
        for k, v in scores.items():
            agg.setdefault(k, []).append(v)
    if agg:
        print("\n=== AGGREGATE (mean) ===")
        for k, vals in agg.items():
            print(f"  {k:22s} {statistics.mean(vals):.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    live_mode() if args.live else dataset_mode()


if __name__ == "__main__":
    main()
