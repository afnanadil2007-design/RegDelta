"""Build the citation and supersession graph over the ingested corpus.

python -m ingestion.build_graph
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import bind_run_id, configure_logging
from app.db.session import get_sessionmaker
from app.services.citation_graph import build_graph


async def run() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    bind_run_id("citation-graph")

    async with get_sessionmaker()() as session:
        report = await build_graph(session)

    print(
        f"citations: {report.citations_resolved}/{report.citations_found} resolved "
        f"({report.resolution_rate:.1%})\n"
        f"supersessions: {report.supersessions_resolved}/{report.supersessions_found} resolved"
    )
    if report.unresolved_examples:
        print("unresolved examples:")
        for ref in report.unresolved_examples[:10]:
            print(f"  {ref}")
    return 0


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
