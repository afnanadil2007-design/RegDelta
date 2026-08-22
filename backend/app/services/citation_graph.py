"""Build the citation and supersession graph over an ingested corpus.

Resolution is a two-pass process:

1. **Exact key match.** Every circular's number is normalised once into a
   lookup table; a reference that normalises to the same key binds directly.
2. **Date-qualified fallback.** A reference the table does not contain, but
   which sits beside a ``dated <date>`` phrase, binds to a circular issued on
   that date when exactly one exists.

Anything still unbound is stored with ``resolved=False``. Unresolved references
are evidence about corpus coverage — the gold-set builder reports the ratio —
and an LLM pass (``resolve_ambiguous``) can be run over just those.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction.citations import (
    detect_supersession,
    find_dated_references,
    find_references,
    normalise_reference,
)
from app.core.logging import get_logger
from app.db.models.corpus import Citation, Paragraph, Supersession
from app.db.models.enums import ResolutionMethod, SupersessionType
from app.repositories.circulars import CircularRepository, ParagraphRepository
from app.repositories.citations import CitationRepository, SupersessionRepository

log = get_logger("app.services.citation_graph")

# A reference must not resolve to the circular that contains it: circulars
# print their own number in the header, which would otherwise create a
# self-edge on every document.
_SELF_EDGE = "self"


@dataclass
class GraphReport:
    citations_found: int = 0
    citations_resolved: int = 0
    supersessions_found: int = 0
    supersessions_resolved: int = 0
    unresolved_examples: list[str] = field(default_factory=list)

    @property
    def resolution_rate(self) -> float:
        return self.citations_resolved / self.citations_found if self.citations_found else 0.0


async def _build_lookup(session: AsyncSession) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Normalised-number → circular id, and ISO issue date → circular ids."""
    circulars = await CircularRepository(session).list_circulars(limit=100_000)
    by_number: dict[str, int] = {}
    by_date: dict[str, list[int]] = {}
    for circular in circulars:
        by_number[normalise_reference(circular.circular_number)] = circular.id
        if circular.issue_date:
            by_date.setdefault(circular.issue_date.isoformat(), []).append(circular.id)
    return by_number, by_date


def _resolve(
    normalised: str,
    paragraph_text: str,
    by_number: dict[str, int],
    by_date: dict[str, list[int]],
) -> tuple[int | None, ResolutionMethod]:
    """Bind one reference to a circular id, or report why it could not bind."""
    target = by_number.get(normalised)
    if target is not None:
        return target, ResolutionMethod.REGEX

    # Date-qualified fallback: unambiguous only when one circular carries the date.
    for dated in find_dated_references(paragraph_text):
        if dated.parsed is None:
            continue
        candidates = by_date.get(dated.parsed.isoformat(), [])
        if len(candidates) == 1:
            return candidates[0], ResolutionMethod.DATE

    return None, ResolutionMethod.UNRESOLVED


async def build_graph_for_circular(
    session: AsyncSession,
    circular_id: int,
    by_number: dict[str, int],
    by_date: dict[str, list[int]],
    report: GraphReport,
) -> None:
    """Extract citations and supersession edges from one circular's paragraphs."""
    paragraphs: list[Paragraph] = await ParagraphRepository(session).list_for_circular(circular_id)
    citations: list[Citation] = []
    supersessions: list[Supersession] = []

    for paragraph in paragraphs:
        refs = find_references(paragraph.text, offset=paragraph.char_start)
        if not refs:
            continue

        cue = detect_supersession(paragraph.text)

        for ref in refs:
            target, method = _resolve(ref.normalised, paragraph.text, by_number, by_date)
            if target == circular_id:
                continue  # the document's own number in its header

            resolved = target is not None
            report.citations_found += 1
            report.citations_resolved += int(resolved)
            if not resolved and len(report.unresolved_examples) < 20:
                report.unresolved_examples.append(ref.raw)

            citations.append(
                Citation(
                    citing_circular_id=circular_id,
                    citing_paragraph_id=paragraph.id,
                    raw_reference=ref.raw,
                    normalised_reference=ref.normalised[:255],
                    cited_circular_id=target,
                    resolved=resolved,
                    resolution_method=method,
                    char_start=ref.char_start,
                    char_end=ref.char_end,
                )
            )

            if cue is not None:
                report.supersessions_found += 1
                report.supersessions_resolved += int(resolved)
                supersessions.append(
                    Supersession(
                        superseding_circular_id=circular_id,
                        superseded_circular_id=target,
                        raw_reference=ref.raw,
                        evidence_paragraph_id=paragraph.id,
                        supersession_type=SupersessionType(cue),
                        # Effective from the superseding circular's own issue
                        # date; set by the caller which knows that date.
                        effective_date=None,
                        resolved=resolved,
                    )
                )

    if citations:
        await CitationRepository(session).add_all(citations)
    if supersessions:
        await SupersessionRepository(session).add_all(supersessions)


async def build_graph(session: AsyncSession) -> GraphReport:
    """Rebuild the citation graph across the whole corpus."""
    by_number, by_date = await _build_lookup(session)
    report = GraphReport()

    circulars = await CircularRepository(session).list_circulars(limit=100_000)
    for circular in circulars:
        await build_graph_for_circular(session, circular.id, by_number, by_date, report)
        # A supersession takes effect when the superseding circular issues.
        await _stamp_effective_dates(session, circular.id, circular.issue_date)

    await session.commit()
    log.info(
        "citation_graph.built",
        extra={
            "circulars": len(circulars),
            "citations": report.citations_found,
            "resolved": report.citations_resolved,
            "resolution_rate": round(report.resolution_rate, 3),
            "supersessions": report.supersessions_found,
        },
    )
    return report


async def _stamp_effective_dates(session: AsyncSession, circular_id: int, issue_date) -> None:
    """Give each new supersession edge the superseding circular's issue date."""
    if issue_date is None:
        return
    edges = await SupersessionRepository(session).list_for_circular(circular_id)
    for edge in edges:
        if edge.superseding_circular_id == circular_id and edge.effective_date is None:
            edge.effective_date = issue_date
    await session.flush()
