"""Run the NER data-quality pass over the sample reports.

    python -m scripts.run_ner

Reads each report in backend/data/documents/, extracts entities with confidence,
auto-updates high-confidence fields in `studies`, and quarantines the rest in
`ner_queue`. Prints a summary table.
"""
from __future__ import annotations

import glob
import os
import sys
sys.path.insert(0, ".")

from backend.app.ner import extract  # noqa: E402


def _read(path: str) -> tuple[str, str]:
    text_lines, study_id = [], os.path.splitext(os.path.basename(path))[0]
    for line in open(path):
        if line.startswith("# STUDY_ID:"):
            study_id = line.split(":", 1)[1].strip()
        if not line.startswith(("#", "@@")):
            text_lines.append(line)
    return study_id, " ".join(text_lines)


def main() -> None:
    for path in sorted(glob.glob("backend/data/documents/*.txt")):
        study_id, text = _read(path)
        entities = extract.extract_entities(text)
        result = extract.apply(study_id, entities)
        print(f"[{study_id}] applied={list(result['applied'])} "
              f"quarantined={list(result['quarantined'])}")
    print("\nQuarantined fields await human review in `ner_queue`.")


if __name__ == "__main__":
    main()
