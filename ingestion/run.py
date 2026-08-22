"""Ingest the local corpus into the database.

python -m ingestion.run                  # everything in data/circulars
python -m ingestion.run --limit 10       # a slice, for a quick check
python -m ingestion.run --no-vision      # skip the vision fallback entirely
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.ai.gateway import LLMGateway
from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.session import get_sessionmaker
from app.services.ingestion import CircularMeta, ingest_batch
from ingestion.manifest import DATA_DIR, MANIFEST_PATH, read_manifest


def collect_items(limit: int | None) -> list[tuple[Path, CircularMeta]]:
    """Pair on-disk PDFs with their manifest metadata.

    A PDF with no manifest entry still gets ingested, using its filename as the
    circular number — the citation resolver will mark references to it
    unresolved rather than silently dropping the document.
    """
    entries = {e.pdf_filename: e for e in read_manifest(MANIFEST_PATH)}
    items: list[tuple[Path, CircularMeta]] = []

    for pdf in sorted(DATA_DIR.glob("*.pdf")):
        entry = entries.get(pdf.name)
        if entry is not None:
            meta = CircularMeta(
                circular_number=entry.circular_number,
                title=entry.title,
                issue_date=entry.parsed_date,
                department=entry.department,
                doc_type=entry.doc_type,
                source_url=entry.source_url,
            )
        else:
            meta = CircularMeta(
                circular_number=pdf.stem.replace("_", "/"),
                title=pdf.stem.replace("_", "/"),
            )
        items.append((pdf, meta))

    return items[:limit] if limit else items


async def run(limit: int | None, use_vision: bool) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    bind_run_id("ingest")

    items = collect_items(limit)
    if not items:
        print(f"No PDFs found in {DATA_DIR}.")
        print("Fetch them with: python -m ingestion.scrape_sebi --fetch-missing")
        return 1

    gateway = LLMGateway(settings) if use_vision else None
    print(f"Ingesting {len(items)} PDFs (vision {'on' if use_vision else 'off'})…")

    async with get_sessionmaker()() as session:
        report = await ingest_batch(session, items, settings=settings, gateway=gateway)

    print(
        f"\ningested={len(report.ingested)}  skipped={len(report.skipped)}  "
        f"failed={len(report.failed)}\n"
        f"pages={report.total_pages}  vision_pages={report.vision_pages}  "
        f"vision_fraction={report.vision_fraction:.1%}"
    )
    for number, error in report.failed:
        print(f"  FAILED {number}: {error}", file=sys.stderr)

    return 0 if not report.failed else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest circulars into RegDelta.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="skip the vision fallback (low-quality pages keep their text layer)",
    )
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.limit, use_vision=not args.no_vision))


if __name__ == "__main__":
    raise SystemExit(main())
