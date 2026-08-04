"""Embeddings — OpenAI-compatible /embeddings, with a deterministic mock.

In mock mode we produce a stable hashed embedding so that vector search still
returns *consistent* (if not semantically perfect) results offline. Dimension
matches EMBED_DIM so it drops straight into the Couchbase vector index.
"""
from __future__ import annotations

import hashlib
import math
from typing import Iterable

from .config import settings


def _mock_embed(text: str) -> list[float]:
    dim = settings.embed_dim
    vec = [0.0] * dim
    # hash tokens into buckets — cheap but deterministic and non-degenerate
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class Embedder:
    def __init__(self) -> None:
        self.mock = settings.mock_llm
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=settings.embed_base_url,
                api_key=settings.embed_api_key or "not-needed",
            )
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.mock:
            return [_mock_embed(t) for t in texts]
        resp = self.client.embeddings.create(model=settings.embed_model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


embedder = Embedder()
