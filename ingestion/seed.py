"""Build a fully working demo database from scratch.

    python -m ingestion.seed

Runs the whole pipeline in order: corpus → ingest → citation graph → policy
pack → embeddings → obligations (rule extractor) → gold set. Every step is
idempotent, so re-running is safe.

The citation graph and the gold set are rebuilt from everything in the
database, so the seed refuses a database that holds circulars from outside the
synthetic corpus (the official SEBI documents, for instance): it would mix the
two corpora and overwrite the tracked gold set from the mixture.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from app.core.config import DatabaseConfigError, get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.session import get_engine, get_sessionmaker
from app.services.policy_pack import index_pack
from ingestion.prepare_db import target

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data" / "policy_packs" / "internal_compliance_manual_v1.md"
# The source_url scheme every generated circular carries.
SYNTHETIC_SCHEME = "synthetic://"
PACK_NAME = "Meridian Broking Internal Compliance Manual"
PACK_VERSION = "1.0"


def _run_module(module: str, *args: str) -> None:
    print(f"\n=== {module} {' '.join(args)} ===", flush=True)
    result = subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{module} failed with exit code {result.returncode}")


async def non_synthetic_circulars() -> int:
    """Circulars in the target database that the synthetic generator did not write."""
    from sqlalchemy import func, or_, select

    from app.db.models.corpus import Circular

    outside = or_(Circular.source_url.is_(None), ~Circular.source_url.startswith(SYNTHETIC_SCHEME))
    async with get_sessionmaker()() as session:
        count = await session.scalar(select(func.count()).where(outside))
    # The pooled connection belongs to this event loop; the policy pack step
    # later runs in another.
    await get_engine().dispose()
    return int(count or 0)


async def seed_policy_pack() -> int:
    async with get_sessionmaker()() as session:
        pack = await index_pack(
            session,
            POLICY_PATH,
            name=PACK_NAME,
            version=PACK_VERSION,
            description=(
                "Synthetic internal compliance manual for a mid-sized Indian broker. "
                "Not a real firm and not legal advice."
            ),
            is_synthetic=True,
        )
        await session.commit()
        return pack.id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo database.")
    parser.add_argument("--count", type=int, default=300, help="synthetic circulars to generate")
    parser.add_argument("--skip-corpus", action="store_true", help="reuse the PDFs on disk")
    args = parser.parse_args(argv)

    get_settings()
    configure_logging("WARNING")
    bind_run_id("seed")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        name = target()
    except DatabaseConfigError as exc:
        print(f"REFUSED: {exc}")
        return 1
    print(f"seeding {name}", flush=True)
    if outside := asyncio.run(non_synthetic_circulars()):
        print(
            f"REFUSED: {name} holds {outside} circular(s) that are not from the synthetic "
            "corpus. Seed a separate database instead, e.g. POSTGRES_DB=regdelta_demo make db seed."
        )
        return 1

    if not args.skip_corpus:
        _run_module("ingestion.generate_corpus", "--count", str(args.count))
    _run_module("ingestion.run", "--no-vision")
    _run_module("ingestion.build_graph")

    print("\n=== policy pack ===", flush=True)
    pack_id = asyncio.run(seed_policy_pack())
    print(f"Policy pack id {pack_id} indexed.")

    _run_module("ingestion.embed")
    _run_module("ingestion.extract_obligations", "--mode", "rules")
    _run_module("evaluation.build_gold_set")

    print(
        "\nSeed complete. Next:\n  make dev-api      (terminal 1)\n  make dev-web      (terminal 2)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
