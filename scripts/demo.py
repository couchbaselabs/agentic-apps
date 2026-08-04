"""End-to-end CLI demo of the PRINCE agentic pipeline (no UI needed).

    python -m scripts.demo                      # runs the flagship example queries
    python -m scripts.demo "your question here"

Works fully offline with MOCK_LLM=true once the cluster is seeded/ingested.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from backend.app import service  # noqa: E402

EXAMPLES = [
    "Were any of the following clinical findings observed in study T123456-2: "
    "piloerection, ataxia, eyes partially closed, and loose faeces?",
    "Give me 50 example studies done on RAT",
    "What is the lowest NOAEL recorded for BAY-45-A and in which study?",
    "Did BAY-45-A cause any cardiovascular effects in dogs?",
]


def show(q: str) -> None:
    print("=" * 90)
    print("Q:", q)
    print("-" * 90)
    r = service.run_chat(q)
    if r["needs_clarification"]:
        print("CLARIFY:", r["clarify_question"])
        return
    print("ANSWER:\n", r["answer"], "\n")
    if r.get("sql"):
        print("SQL++:", r["sql"])
        print("ROWS:", len(r.get("rows", [])))
    if r.get("citations"):
        print("CITATIONS:")
        for c in r["citations"]:
            print("  -", c.get("chunk_id") or c.get("study_id"),
                  "| p." + str(c.get("page")) if c.get("page") else "")
    print("\nINTERMEDIATE STEPS:")
    for s in r["steps"]:
        print("  ·", s.get("step"), {k: v for k, v in s.items() if k != "step"})
    print()


def main() -> None:
    qs = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else EXAMPLES
    for q in qs:
        show(q)


if __name__ == "__main__":
    main()
