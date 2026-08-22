"""Extract obligations from ingested circulars.

Two modes:

``--mode llm`` (default, production)
    Uses ``app.ai.extraction.obligations``: a model call per paragraph,
    schema-validated with one repair attempt, and every quoted span resolved
    against the source paragraph. Requires a working provider key.

``--mode rules`` (seeding aid, offline)
    A modality regex over numbered paragraphs. This exists so the demo
    database can be seeded, the UI populated, and the agent exercised without
    a provider key. It is **not** the extraction the project is measuring:
    ``evaluation/metrics/extraction.py`` scores the LLM path against hand
    labels, and a rules-extracted corpus should never be used for that.

    python -m ingestion.extract_obligations --mode rules
    python -m ingestion.extract_obligations --mode llm --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

from app.ai.extraction.obligations import extract_from_paragraph
from app.ai.gateway import LLMGateway
from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging, get_logger
from app.db.models.corpus import Obligation
from app.db.session import get_sessionmaker
from app.repositories.circulars import CircularRepository, ParagraphRepository
from app.repositories.obligations import ObligationRepository

log = get_logger("ingestion.extract_obligations")

# "<Actor> shall|must|may|should <action>" inside a numbered paragraph.
_RULE = re.compile(
    r"(?P<actor>(?:[A-Z][\w'\-]*\s+){0,4}?[A-Za-z][\w'\-]*)\s+"
    r"(?P<modality>shall|must|may|should)\s+"
    r"(?P<action>[^.]{10,400}\.)",
)
# Sentences that are structurally obligations but carry no requirement.
_EXCLUDE = re.compile(
    r"(issued in exercise of powers|stand superseded|shall stand modified|"
    r"shall be read together|continue to apply|shall come into force)",
    re.I,
)


def rule_extract(text: str, base_offset: int) -> list[dict]:
    """Regex fallback. Returns dicts shaped like the LLM path's output."""
    out: list[dict] = []
    for match in _RULE.finditer(text):
        span_text = match.group(0).strip()
        if _EXCLUDE.search(span_text) or len(span_text) < 25:
            continue
        start = base_offset + match.start()
        out.append(
            {
                "text": span_text,
                "actor": match.group("actor").strip(),
                "action": match.group("action").strip().rstrip("."),
                "modality": match.group("modality").lower(),
                "confidence": 0.55,  # a regex is a weak signal; say so
                "char_start": start,
                "char_end": start + len(span_text),
            }
        )
    return out


async def run(mode: str, limit: int | None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    bind_run_id(f"obligations-{mode}")
    gateway = LLMGateway(settings) if mode == "llm" else None

    total = 0
    failures = 0
    dropped = 0

    async with get_sessionmaker()() as session:
        circulars = await CircularRepository(session).list_circulars(limit=limit or 100_000)
        existing = await ObligationRepository(session).count()
        if existing:
            print(f"{existing} obligations already present; skipping extraction.")
            return 0

        for index, circular in enumerate(circulars, start=1):
            paragraphs = await ParagraphRepository(session).list_for_circular(circular.id)
            rows: list[Obligation] = []
            seen: set[tuple[int, int]] = set()

            for paragraph in paragraphs:
                if mode == "rules":
                    items = rule_extract(paragraph.text, paragraph.char_start)
                else:
                    outcome = extract_from_paragraph(gateway, paragraph.text, paragraph.char_start)
                    failures += int(outcome.failed)
                    dropped += outcome.dropped_unresolvable
                    items = [
                        {
                            "text": c.extracted.text,
                            "actor": c.extracted.actor,
                            "action": c.extracted.action,
                            "modality": c.extracted.modality,
                            "confidence": c.extracted.confidence,
                            "char_start": c.span.char_start,
                            "char_end": c.span.char_end,
                        }
                        for c in outcome.candidates
                    ]

                for item in items:
                    key = (item["char_start"], item["char_end"])
                    if key in seen:
                        continue  # the schema has a unique span constraint
                    seen.add(key)
                    rows.append(
                        Obligation(
                            circular_id=circular.id,
                            paragraph_id=paragraph.id,
                            text=item["text"],
                            actor=item["actor"],
                            action=item["action"],
                            modality=item["modality"],
                            char_start=item["char_start"],
                            char_end=item["char_end"],
                            confidence=item["confidence"],
                        )
                    )

            if rows:
                await ObligationRepository(session).add_all(rows)
                await session.commit()
                total += len(rows)
            if index % 50 == 0:
                print(f"  {index}/{len(circulars)} circulars, {total} obligations", flush=True)

    print(f"\nExtracted {total} obligations ({mode} mode).")
    if mode == "llm":
        print(f"  extraction failures: {failures}")
        print(f"  dropped (span unresolvable): {dropped}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract obligations.")
    parser.add_argument("--mode", choices=["llm", "rules"], default="llm")
    parser.add_argument("--limit", type=int, default=None, help="circulars to process")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.mode, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
