"""MCP server exposing RegDelta's retrieval to any conforming client.

WHY THIS EXISTS
---------------
The retrieval capability — a point-in-time-aware, citation-grounded index over
SEBI circulars — is useful outside this application. An analyst in Claude
Desktop, an internal agent, or a notebook all want the same three questions
answered, and none of them want to integrate against a bespoke HTTP API.
Exposing it over MCP makes the capability consumable by any conforming client
with no integration code on either side.

It reuses ``app.ai.retrieval.pipeline`` directly — the same code path the HTTP
API and the evaluation harness use. Duplicating retrieval here would mean the
MCP surface could drift from the measured one.

    python -m mcp_server.server
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

from fastmcp import FastMCP

from app.ai.retrieval.pipeline import retrieve
from app.db.models.enums import RetrievalMode
from app.db.session import get_sessionmaker
from app.repositories.circulars import CircularRepository
from app.repositories.obligations import ObligationRepository
from app.repositories.search import SearchFilters

mcp = FastMCP("regdelta")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"as_of must be ISO-8601 (YYYY-MM-DD); got {value!r}") from exc


@mcp.tool()
async def search_circulars(query: str, as_of: str | None = None, top_k: int = 5) -> dict:
    """Search SEBI circulars.

    Args:
        query: what to search for, in natural language or as a reference number.
        as_of: optional ISO date; excludes circulars superseded by then.
        top_k: how many passages to return (default 5).

    Returns passages with their circular number, issue date, and character
    offsets into that circular's full text.
    """
    try:
        filters = SearchFilters(as_of=_parse_date(as_of))
    except ValueError as exc:
        return {"error": str(exc)}

    async with get_sessionmaker()() as session:
        result = await retrieve(
            session,
            query,
            mode=RetrievalMode.HYBRID_RERANK,
            filters=filters,
            top_k=top_k,
        )
        if result.below_threshold:
            return {
                "results": [],
                "refused": True,
                "reason": "No passage cleared the relevance threshold.",
            }

        circulars = CircularRepository(session)
        out = []
        for hit in result.hits:
            circular = await circulars.get(hit.circular_id)
            out.append(
                {
                    "circular_number": circular.circular_number if circular else None,
                    "title": circular.title if circular else None,
                    "issue_date": circular.issue_date.isoformat()
                    if circular and circular.issue_date
                    else None,
                    "text": hit.text,
                    "char_start": hit.char_start,
                    "char_end": hit.char_end,
                    "score": round(hit.score, 4),
                }
            )
        return {
            "results": out,
            "refused": False,
            "excluded_by_temporal_filter": len(result.excluded_by_temporal_filter),
        }


@mcp.tool()
async def get_obligations(circular_number: str) -> dict:
    """List the obligations extracted from one circular.

    Args:
        circular_number: the full SEBI reference, e.g.
            ``SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/17``.

    Each obligation carries character offsets into the circular's full text,
    so a caller can verify the quote rather than trusting it.
    """
    async with get_sessionmaker()() as session:
        circular = await CircularRepository(session).get_by_number(circular_number)
        if circular is None:
            return {"error": f"No circular with number {circular_number!r} in this corpus."}

        obligations = await ObligationRepository(session).list_for_circular(circular.id)
        return {
            "circular_number": circular.circular_number,
            "title": circular.title,
            "obligations": [
                {
                    "text": o.text,
                    "actor": o.actor,
                    "modality": o.modality,
                    "deadline": o.deadline,
                    "char_start": o.char_start,
                    "char_end": o.char_end,
                }
                for o in obligations
            ],
        }


@mcp.tool()
async def as_of_lookup(question: str, as_of: str) -> dict:
    """Answer what was in force on a given date.

    Args:
        question: the question, in natural language.
        as_of: ISO date. Circulars superseded on or before this date are
            excluded, and the count of exclusions is reported.

    Returns the passages in force on that date, or an explicit refusal when
    nothing clears the relevance threshold.
    """
    try:
        parsed = _parse_date(as_of)
    except ValueError as exc:
        return {"error": str(exc)}
    if parsed is None:
        return {"error": "as_of is required for a point-in-time lookup."}

    result = await search_circulars(question, as_of=as_of, top_k=8)
    result["as_of"] = as_of
    return result


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
