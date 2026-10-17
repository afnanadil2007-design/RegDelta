"""Ingest the local corpus into the database.

python -m ingestion.run                     # the synthetic corpus in data/synthetic
python -m ingestion.run --corpus real       # official documents in data/real_sources
python -m ingestion.run --limit 10          # a slice, for a quick check
python -m ingestion.run --no-vision         # skip the vision fallback entirely
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
from ingestion.manifest import CorpusName, corpus_paths, read_manifest


def collect_items(corpus: CorpusName, limit: int | None) -> list[tuple[Path, CircularMeta]]:
    """Pair on-disk PDFs with their manifest metadata.

    A PDF with no manifest entry still gets ingested, using its filename as the
    circular number — the citation resolver will mark references to it
    unresolved rather than silently dropping the document.
    """
    paths = corpus_paths(corpus)
    entries = {e.pdf_filename: e for e in read_manifest(paths.manifest)}
    items: list[tuple[Path, CircularMeta]] = []

    for pdf in sorted(paths.pdf_dir.glob("*.pdf")):
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


async def run(corpus: CorpusName, limit: int | None, use_vision: bool) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    bind_run_id("ingest")

    items = collect_items(corpus, limit)
    if not items:
        print(f"No PDFs found in {corpus_paths(corpus).pdf_dir}.")
        hint = "ingestion.generate_corpus" if corpus == "synthetic" else "ingestion.scrape_sebi"
        print(f"Create them with: python -m {hint}")
        return 1

    gateway = LLMGateway(settings) if use_vision else None
    print(f"Ingesting {len(items)} PDFs (vision {'on' if use_vision else 'off'})…")

    async with get_sessionmaker()() as session:
        report = await ingest_batch(session, items, settings=settings, gateway=gateway)

    print(
        f"\ningested={len(report.ingested)}  skipped={len(report.skipped)}  "
        f"conflicts={len(report.conflicts)}  failed={len(report.failed)}\n"
        f"pages={report.total_pages}  vision_pages={report.vision_pages}  "
        f"vision_fraction={report.vision_fraction:.1%}"
    )
    for number, reason in report.conflicts:
        print(f"  CONFLICT {number}: {reason}", file=sys.stderr)
    for number, error in report.failed:
        print(f"  FAILED {number}: {error}", file=sys.stderr)

    return 0 if not (report.failed or report.conflicts) else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest circulars into RegDelta.")
    parser.add_argument("--corpus", choices=["synthetic", "real"], default="synthetic")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="skip the vision fallback (low-quality pages keep their text layer)",
    )
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.corpus, args.limit, use_vision=not args.no_vision))


if __name__ == "__main__":
    raise SystemExit(main())
