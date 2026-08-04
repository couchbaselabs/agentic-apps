"""Ingestion pipeline (the PRINCE "RAG ingestion").

  PDFs / text reports  ->  normalized JSON chunks  ->  metadata enrichment
  (study_id, compound, species, route, page, parent_section from `studies`)
  ->  embed  ->  index into Couchbase `documents` (FTS text + FTS vector).

Supports two source formats in backend/data/documents/:
  * .txt  — marker format with @@PAGE n / @@SECTION x.y Title (see samples)
  * .pdf  — extracted with pypdf; page = PDF page, section inferred by heading regex

Run:
    python -m scripts.ingest
    python -m scripts.ingest --file backend/data/documents/T123456-2.txt
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, ".")
from backend.app.config import settings                       # noqa: E402
from backend.app.couchbase_client import kv_upsert, kv_get    # noqa: E402
from backend.app.embeddings import embedder                   # noqa: E402

DATA_DOCS = "backend/data/documents"
DATA_STUDIES = "backend/data/studies/studies.json"

CHUNK_CHARS = 900          # target chunk size (chars) — preserves scientific context
CHUNK_OVERLAP = 150


@dataclass
class Chunk:
    study_id: str
    page: int
    parent_section: str
    text: str
    compound: str = ""
    species: str = ""
    route: str = ""
    embedding: list[float] = field(default_factory=list)

    @property
    def chunk_id(self) -> str:
        sec = re.sub(r"[^0-9a-zA-Z]+", "", self.parent_section)[:12] or "sec"
        # stable, human-legible key: study::section::page::seq handled by caller
        return f"{self.study_id}::{sec}::p{self.page:03d}"


def _study_index() -> dict[str, dict]:
    studies = json.load(open(DATA_STUDIES))
    return {s["study_id"]: s for s in studies}


def _split_text(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        # try to break on sentence boundary
        dot = text.rfind(". ", start, end)
        if dot > start + CHUNK_CHARS // 2:
            end = dot + 1
        out.append(text[start:end].strip())
        start = end - CHUNK_OVERLAP
    return [c for c in out if c]


def parse_txt(path: str) -> list[Chunk]:
    study_id, page, section = "", 1, "Unknown"
    header = {}
    buffers: list[tuple[int, str, str]] = []  # (page, section, text)
    cur: list[str] = []

    def flush():
        if cur:
            buffers.append((page, section, " ".join(cur)))
            cur.clear()

    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("# "):
            m = re.match(r"# (\w+):\s*(.+)", line)
            if m:
                header[m.group(1).lower()] = m.group(2).strip()
            continue
        if line.startswith("@@PAGE"):
            flush()
            page = int(re.search(r"\d+", line).group())
            continue
        if line.startswith("@@SECTION"):
            flush()
            section = line.replace("@@SECTION", "").strip()
            continue
        if line.strip():
            cur.append(line.strip())
    flush()

    study_id = header.get("study_id", os.path.splitext(os.path.basename(path))[0])
    chunks: list[Chunk] = []
    for pg, sec, text in buffers:
        for piece in _split_text(text):
            chunks.append(Chunk(study_id=study_id, page=pg, parent_section=sec, text=piece))
    return chunks


def parse_pdf(path: str) -> list[Chunk]:
    from pypdf import PdfReader
    study_id = os.path.splitext(os.path.basename(path))[0]
    reader = PdfReader(path)
    chunks: list[Chunk] = []
    section = "Body"
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        m = re.search(r"\n\s*(\d+(?:\.\d+)?\s+[A-Z][A-Za-z ]{3,40})", text)
        if m:
            section = m.group(1).strip()
        for piece in _split_text(text):
            chunks.append(Chunk(study_id=study_id, page=i, parent_section=section, text=piece))
    return chunks


def enrich(chunks: list[Chunk], studies: dict[str, dict]) -> None:
    for c in chunks:
        s = studies.get(c.study_id, {})
        c.compound = s.get("compound", "")
        c.species = s.get("species", "")
        c.route = s.get("route", "")


def index(chunks: list[Chunk]) -> int:
    # embed in batches
    texts = [c.text for c in chunks]
    vectors = []
    for i in range(0, len(texts), 64):
        vectors.extend(embedder.embed(texts[i:i + 64]))
    for c, v in zip(chunks, vectors):
        c.embedding = v

    seq: dict[str, int] = {}
    n = 0
    for c in chunks:
        base = c.chunk_id
        s = seq.get(base, 0)
        seq[base] = s + 1
        key = f"{base}::c{s}"
        doc = {
            "type": "chunk",
            "chunk_id": key,
            "study_id": c.study_id,
            "compound": c.compound,
            "species": c.species,
            "route": c.route,
            "page": c.page,
            "parent_section": c.parent_section,
            "text": c.text,
            "embedding": c.embedding,
        }
        kv_upsert(settings.coll_documents, key, doc)
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="single file to ingest", default=None)
    args = ap.parse_args()

    studies = _study_index()
    files = [args.file] if args.file else (
        sorted(glob.glob(f"{DATA_DOCS}/*.txt")) + sorted(glob.glob(f"{DATA_DOCS}/*.pdf"))
    )
    total = 0
    for path in files:
        parser = parse_pdf if path.endswith(".pdf") else parse_txt
        chunks = parser(path)
        enrich(chunks, studies)
        added = index(chunks)
        total += added
        print(f"[+] {os.path.basename(path)}: {added} chunks indexed")
    print(f"\nDone. {total} chunks in `{settings.coll_documents}`. "
          f"(mock_embeddings={settings.mock_llm})")


if __name__ == "__main__":
    main()
