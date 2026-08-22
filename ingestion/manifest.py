"""The circular manifest: metadata for every PDF in the corpus.

The repository ships a manifest (JSONL) rather than ~300 PDFs — a few hundred
SEBI PDFs would bloat the clone, and the documents are public and stable at
their source URLs. ``scrape_sebi.py`` fetches the PDFs the manifest names;
``run.py`` ingests whatever is present on disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "circulars"
MANIFEST_PATH = DATA_DIR / "manifest.jsonl"


@dataclass
class ManifestEntry:
    circular_number: str
    title: str
    issue_date: str | None  # ISO-8601; str so the manifest is plain JSON
    department: str | None
    doc_type: str
    source_url: str
    pdf_filename: str

    @property
    def parsed_date(self) -> date | None:
        return date.fromisoformat(self.issue_date) if self.issue_date else None


def write_manifest(entries: list[ManifestEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


def read_manifest(path: Path) -> list[ManifestEntry]:
    if not path.is_file():
        return []
    entries: list[ManifestEntry] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(ManifestEntry(**json.loads(line)))
    return entries
