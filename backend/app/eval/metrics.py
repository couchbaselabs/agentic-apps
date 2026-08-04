"""Evaluation metrics (RAGAS-style), all computable against this stack.

Metrics (as named in the article):
  * faithfulness            — is the answer supported by the retrieved context?
  * answer_relevancy        — does the answer address the question?
  * context_relevancy       — are the retrieved chunks relevant?
  * answer_accuracy         — does the answer match ground truth?
  * semantic_similarity     — embedding cosine between answer and reference.

LLM-judged metrics use the strong model; semantic_similarity uses embeddings.
In MOCK_LLM mode the judge is heuristic, so scores are indicative not rigorous.
"""
from __future__ import annotations

import math
from typing import Any

from ..llm import llm
from ..embeddings import embedder
from .. import prompts

_METRIC_DESC = {
    "faithfulness": "fraction of the answer's claims that are supported by the context",
    "answer_relevancy": "how directly the answer addresses the question",
    "context_relevancy": "how relevant the retrieved context is to the question",
    "answer_accuracy": "how well the answer matches the reference/ground-truth",
}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _judge(metric: str, question: str, reference: str, context: str, generated: str) -> float:
    out = llm.json(
        [{"role": "user", "content": prompts.EVAL_JUDGE.format(
            metric=metric, metric_desc=_METRIC_DESC[metric],
            question=question, reference=reference,
            context=context[:4000], generated=generated)}],
        task="eval_judge",
    )
    try:
        return max(0.0, min(1.0, float(out.get("score", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def semantic_similarity(generated: str, reference: str) -> float:
    va, vb = embedder.embed([generated, reference])
    return round((_cosine(va, vb) + 1) / 2, 4)  # map [-1,1] -> [0,1]


def keyword_recall(generated: str, must_include: list[str]) -> float:
    if not must_include:
        return 1.0
    g = generated.lower()
    hit = sum(1 for k in must_include if k.lower() in g)
    return round(hit / len(must_include), 4)


def evaluate_one(item: dict[str, Any], generated: str, context: str,
                 live: bool = False) -> dict[str, Any]:
    """live=True skips reference-based metrics (no ground truth in production)."""
    q = item["question"]
    ref = item.get("reference_answer", "")
    scores: dict[str, Any] = {
        "faithfulness": round(_judge("faithfulness", q, ref, context, generated), 4),
        "answer_relevancy": round(_judge("answer_relevancy", q, ref, context, generated), 4),
        "context_relevancy": round(_judge("context_relevancy", q, ref, context, generated), 4),
    }
    if not live and ref:
        scores["answer_accuracy"] = round(_judge("answer_accuracy", q, ref, context, generated), 4)
        scores["semantic_similarity"] = semantic_similarity(generated, ref)
        scores["keyword_recall"] = keyword_recall(generated, item.get("must_include", []))
    return scores
