"""Named Entity Recognition data-quality module.

Mirrors the PRINCE utility that repairs incomplete/incorrect historical metadata:
  * read study report text
  * extract entities (study_id, compound, species, route, study_type, NOAEL, findings)
    with a per-field confidence score
  * HIGH confidence -> auto-update the structured `studies` document
  * LOW confidence  -> quarantine in `ner_queue` for human review

Threshold is configurable; default 0.85.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..llm import llm
from ..config import settings
from ..couchbase_client import kv_get, kv_upsert
from .. import prompts

AUTO_UPDATE_THRESHOLD = 0.85


def extract_entities(text: str) -> dict[str, dict[str, Any]]:
    out = llm.json(
        [{"role": "user", "content": prompts.NER_EXTRACTION.format(text=text[:6000])}],
        task="ner_extraction",
    )
    return out.get("entities", {})


def apply(study_id: str, entities: dict[str, dict[str, Any]],
          threshold: float = AUTO_UPDATE_THRESHOLD) -> dict[str, Any]:
    """Apply high-confidence fields to `studies`; quarantine the rest."""
    study = kv_get(settings.coll_studies, study_id) or {"type": "study", "study_id": study_id}
    applied, quarantined = {}, {}

    for field, info in entities.items():
        value = info.get("value")
        conf = float(info.get("confidence", 0.0))
        if value is None:
            continue
        if conf >= threshold:
            # only fill blanks / correct if changed
            if study.get(field) != value:
                study[field] = value
                applied[field] = {"value": value, "confidence": conf}
        else:
            quarantined[field] = {"value": value, "confidence": conf,
                                  "current": study.get(field)}

    if applied:
        study["ner_last_updated"] = datetime.now(timezone.utc).isoformat()
        kv_upsert(settings.coll_studies, study_id, study)

    if quarantined:
        kv_upsert(settings.coll_ner_queue, f"ner::{study_id}", {
            "type": "ner_review",
            "study_id": study_id,
            "fields": quarantined,
            "status": "pending_review",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    return {"study_id": study_id, "applied": applied, "quarantined": quarantined}
