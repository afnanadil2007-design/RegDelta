"""Stage 4 tests: citation regex, supersession cues, and graph resolution."""

from __future__ import annotations

from datetime import date

import pytest

from app.ai.extraction.citations import (
    detect_supersession,
    find_dated_references,
    find_references,
    normalise_reference,
    parse_date_token,
)
from app.services.citation_graph import build_graph
from tests.reference_fixtures import NEGATIVE_STRINGS, REFERENCE_STRINGS

# --- the 40-reference fixture the brief requires ------------------------


@pytest.mark.parametrize("reference", REFERENCE_STRINGS, ids=range(len(REFERENCE_STRINGS)))
def test_every_reference_format_is_matched_exactly(reference: str) -> None:
    found = find_references(reference)
    assert found, f"no match for {reference!r}"
    assert found[0].raw == reference, f"partial match: {found[0].raw!r} != {reference!r}"


@pytest.mark.parametrize("text", NEGATIVE_STRINGS)
def test_near_miss_strings_do_not_match(text: str) -> None:
    """A false edge in the citation graph is worse than a missing one."""
    assert find_references(text) == []


def test_references_are_found_inside_running_prose() -> None:
    prose = (
        "3. This circular supersedes SEBI/HO/MIRSD/CIR/P/2020/99 dated October 06, "
        "2020 and partially modifies CIR/MRD/DP/54/2017, issued under Section 11(1)."
    )
    found = find_references(prose)
    assert [f.raw for f in found] == [
        "SEBI/HO/MIRSD/CIR/P/2020/99",
        "CIR/MRD/DP/54/2017",
    ]
    # Offsets must point at the reference inside the source text.
    for ref in found:
        assert prose[ref.char_start : ref.char_end] == ref.raw


def test_offsets_are_shifted_by_the_paragraph_base() -> None:
    prose = "See SEBI/HO/CFD/CIR/P/2021/12 for detail."
    found = find_references(prose, offset=1000)
    assert found[0].char_start == 1004
    assert found[0].char_end == 1004 + len("SEBI/HO/CFD/CIR/P/2021/12")


# --- normalisation ------------------------------------------------------


def test_normalisation_makes_separator_variants_comparable() -> None:
    a = normalise_reference("SEBI/HO/MIRSD/CIR/P/2020/99")
    b = normalise_reference("sebi-ho-mirsd-cir-p-2020-99")
    c = normalise_reference("  SEBI/HO/MIRSD/CIR/P/2020/99.  ")
    assert a == b == c


# --- dates --------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("October 06, 2023", date(2023, 10, 6)),
        ("6 October 2023", date(2023, 10, 6)),
        ("06.10.2023", date(2023, 10, 6)),
        ("06-10-2023", date(2023, 10, 6)),
    ],
)
def test_date_tokens_parse(token: str, expected: date) -> None:
    assert parse_date_token(token) == expected


def test_dated_reference_is_located_in_text() -> None:
    text = "the circular dated October 06, 2023 shall apply"
    found = find_dated_references(text)
    assert len(found) == 1
    assert found[0].parsed == date(2023, 10, 6)


# --- supersession cues --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This circular shall supersede the earlier one.", "supersedes"),
        ("The said circular stands superseded.", "supersedes"),
        ("Paragraph 4 stands rescinded with effect from today.", "rescinds"),
        ("The provisions are hereby rescinded.", "rescinds"),
        ("Clause 2 stands modified to the following extent.", "amends"),
        ("This is partially modified by the present circular.", "partial"),
        ("The circulars listed at Annex-1 are replaced.", "supersedes"),
        ("Intermediaries shall collect upfront margin.", None),
    ],
)
def test_supersession_cues(text: str, expected: str | None) -> None:
    assert detect_supersession(text) == expected


def test_strongest_cue_wins_when_several_appear() -> None:
    """'shall supersede' must not be shadowed by a later 'modified'."""
    text = "This circular shall supersede the earlier one, which stands modified."
    assert detect_supersession(text) == "supersedes"


# --- graph construction against the database ----------------------------


@pytest.mark.asyncio
async def test_graph_resolves_citations_between_ingested_circulars(
    session, tmp_path
) -> None:
    """Two circulars where the second cites and supersedes the first."""
    from app.repositories.citations import CitationRepository, SupersessionRepository
    from app.services.ingestion import CircularMeta, ingest_pdf
    from tests.fixtures import FixtureCircular, write_fixture_pdf

    old_number = "SEBI/HO/MIRSD/CIR/P/2020/900"
    new_number = "SEBI/HO/MIRSD/CIR/P/2024/901"

    old = FixtureCircular(old_number, "Older margin circular", [
        f"{old_number}\n\nJanuary 10, 2020\n\nUPFRONT MARGIN\n\n"
        "1. Brokers shall collect upfront margin from clients.\n"
    ])
    new = FixtureCircular(new_number, "Newer margin circular", [
        f"{new_number}\n\nMarch 04, 2024\n\nUPFRONT MARGIN\n\n"
        "1. Brokers shall collect upfront margin before order entry.\n\n"
        f"2. The provisions of {old_number} dated January 10, 2020 shall "
        "stand superseded from the date of this circular.\n"
    ])

    old_c = await ingest_pdf(
        session, write_fixture_pdf(old, tmp_path / "o"),
        CircularMeta(old_number, old.title, issue_date=date(2020, 1, 10)),
    )
    new_c = await ingest_pdf(
        session, write_fixture_pdf(new, tmp_path / "n"),
        CircularMeta(new_number, new.title, issue_date=date(2024, 3, 4)),
    )
    assert old_c and new_c

    await build_graph(session)

    citations = await CitationRepository(session).list_for_circular(new_c.id)
    resolved = [c for c in citations if c.resolved]
    assert resolved, "the reference to the older circular should resolve"
    assert any(c.cited_circular_id == old_c.id for c in resolved)

    edges = await SupersessionRepository(session).list_for_circular(new_c.id)
    assert edges, "supersession language should produce an edge"
    edge = edges[0]
    assert edge.superseded_circular_id == old_c.id
    assert edge.resolved is True
    assert edge.evidence_paragraph_id is not None, "the edge must cite its evidence"
    assert edge.effective_date == date(2024, 3, 4)


@pytest.mark.asyncio
async def test_a_circular_does_not_cite_itself(session, tmp_path) -> None:
    """Circulars print their own number in the header; that is not a citation."""
    from app.repositories.citations import CitationRepository
    from app.services.ingestion import CircularMeta, ingest_pdf
    from tests.fixtures import FixtureCircular, write_fixture_pdf

    number = "SEBI/HO/CFD/CIR/P/2024/902"
    fixture = FixtureCircular(number, "Self reference", [
        f"{number}\n\nMay 01, 2024\n\nDISCLOSURE\n\n1. Issuers shall disclose promptly.\n"
    ])
    circular = await ingest_pdf(
        session, write_fixture_pdf(fixture, tmp_path),
        CircularMeta(number, fixture.title, issue_date=date(2024, 5, 1)),
    )
    assert circular

    await build_graph(session)
    citations = await CitationRepository(session).list_for_circular(circular.id)
    assert all(c.cited_circular_id != circular.id for c in citations)


@pytest.mark.asyncio
async def test_unresolved_references_are_kept_not_discarded(session, tmp_path) -> None:
    """Coverage evidence: a dangling reference is stored with resolved=False."""
    from app.repositories.citations import CitationRepository
    from app.services.ingestion import CircularMeta, ingest_pdf
    from tests.fixtures import FixtureCircular, write_fixture_pdf

    number = "SEBI/HO/ISD/CIR/P/2024/903"
    missing = "SEBI/HO/NOWHERE/CIR/P/1999/1"
    fixture = FixtureCircular(number, "Dangling reference", [
        f"{number}\n\nJune 02, 2024\n\nSURVEILLANCE\n\n"
        f"1. Read with {missing} which is not in this corpus.\n"
    ])
    circular = await ingest_pdf(
        session, write_fixture_pdf(fixture, tmp_path),
        CircularMeta(number, fixture.title, issue_date=date(2024, 6, 2)),
    )
    assert circular

    await build_graph(session)
    citations = await CitationRepository(session).list_for_circular(circular.id)
    dangling = [c for c in citations if not c.resolved]
    assert dangling, "the unresolvable reference must still be recorded"
    assert dangling[0].raw_reference == missing
    assert dangling[0].cited_circular_id is None
