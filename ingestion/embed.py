"""Populate chunk and policy-clause embeddings.

Kept separate from ingestion so the corpus can be re-embedded (new model, new
dimension) without re-parsing every PDF.

    python -m ingestion.embed
    python -m ingestion.embed --force     # re-embed everything
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.ai.retrieval.embeddings import embed_documents
from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging, get_logger
from app.db.models.corpus import Chunk
from app.db.models.policy import PolicyClause
from app.db.session import get_sessionmaker

log = get_logger("ingestion.embed")
BATCH = 128


async def _embed_table(session, model_cls, force: bool) -> int:
    stmt = select(model_cls).order_by(model_cls.id)
    if not force:
        stmt = stmt.where(model_cls.embedding.is_(None))
    rows = list((await session.execute(stmt)).scalars())
    if not rows:
        return 0

    done = 0
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        vectors = embed_documents([r.text for r in batch])
        for row, vector in zip(batch, vectors, strict=True):
            row.embedding = vector
        await session.commit()
        done += len(batch)
        print(f"  {model_cls.__tablename__}: {done}/{len(rows)}", flush=True)
    return done


async def run(force: bool) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    bind_run_id("embed")

    async with get_sessionmaker()() as session:
        chunks = await _embed_table(session, Chunk, force)
        clauses = await _embed_table(session, PolicyClause, force)

    print(f"Embedded {chunks} chunks and {clauses} policy clauses.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embed chunks and policy clauses.")
    parser.add_argument("--force", action="store_true", help="re-embed rows that already have one")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
