"""Build a fully working demo database from scratch.

    python -m ingestion.seed

Runs the whole pipeline in order: corpus → ingest → citation graph → policy
pack → embeddings → gold set. Every step is idempotent, so re-running is safe.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.session import get_sessionmaker
from app.services.policy_pack import index_pack

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data" / "policy_packs" / "internal_compliance_manual_v1.md"
PACK_NAME = "Meridian Broking Internal Compliance Manual"
PACK_VERSION = "1.0"


def _run_module(module: str, *args: str) -> None:
    print(f"\n=== {module} {' '.join(args)} ===", flush=True)
    result = subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{module} failed with exit code {result.returncode}")


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

    settings = get_settings()
    configure_logging("WARNING")
    bind_run_id("seed")
    _ = settings

    if not args.skip_corpus:
        _run_module("ingestion.generate_corpus", "--count", str(args.count))
    _run_module("ingestion.run", "--no-vision")
    _run_module("ingestion.build_graph")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("\n=== policy pack ===", flush=True)
    pack_id = asyncio.run(seed_policy_pack())
    print(f"Policy pack id {pack_id} indexed.")

    _run_module("ingestion.embed")
    _run_module("evaluation.build_gold_set")

    print(
        "\nSeed complete. Next:"
        "\n  python -m ingestion.extract_obligations --mode rules"
        "\n  python backend/run_api.py        (terminal 1)"
        "\n  cd frontend && npm run dev       (terminal 2)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
