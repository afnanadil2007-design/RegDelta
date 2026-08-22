"""Synthetic SEBI-style circular PDFs for tests.

These are fixtures, not real SEBI documents: they imitate the structure the
parser cares about (reference numbers, numbered paragraphs, annexure tables,
supersession language) so tests exercise real behaviour without depending on
network access or shipping copyrighted PDFs into the test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class FixtureCircular:
    circular_number: str
    title: str
    pages: list[str]


FIXTURE_MARGIN = FixtureCircular(
    circular_number="SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17",
    title="Upfront collection of margins from clients",
    pages=[
        """SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/17

February 12, 2024

To
All Stock Brokers through Stock Exchanges

UPFRONT COLLECTION OF MARGINS

1. Stock brokers shall collect upfront margin from clients before
accepting orders in the cash and derivatives segments.

2.1 The margin shall be collected in the form of cash, cash equivalents
or approved securities held as collateral.

2.2 Stock brokers shall report instances of short-collection of margin
to the Stock Exchange by T+1 day.

3. This circular supersedes SEBI/HO/MIRSD/CIR/P/2020/99 dated
October 06, 2020 to the extent of margin reporting timelines.
""",
        """ANNEXURE A

Applicable margin rates by segment are set out below.

4. Stock brokers shall retain evidence of margin collection for a period
of five years and produce it during inspection.
""",
    ],
)

FIXTURE_KYC = FixtureCircular(
    circular_number="SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/31",
    title="Simplification of KYC norms for onboarding",
    pages=[
        """SEBI/HO/MIRSD/MIRSD-PoD/CIR/P/2024/31

April 05, 2024

SIMPLIFICATION OF KYC NORMS

1. Intermediaries shall complete client due diligence before activating
a trading account.

2. Intermediaries shall verify the Permanent Account Number of every
client against the income tax database at the time of onboarding.

3. The provisions of SEBI/HO/MIRSD/CIR/P/2023/12 dated January 20, 2023
shall stand superseded from the date of this circular.
"""
    ],
)

FIXTURE_CYBER = FixtureCircular(
    circular_number="SEBI/HO/ITD/ITD-PoD/CIR/P/2024/44",
    title="Cyber security and cyber resilience framework",
    pages=[
        """SEBI/HO/ITD/ITD-PoD/CIR/P/2024/44

June 18, 2024

CYBER SECURITY AND CYBER RESILIENCE FRAMEWORK

1. Market infrastructure institutions and intermediaries shall establish
a documented cyber security policy approved by the governing board.

2. Intermediaries shall report cyber security incidents to SEBI within
six hours of detection.

3. A Vulnerability Assessment and Penetration Test shall be conducted at
least once every financial year.
"""
    ],
)

ALL_FIXTURES = [FIXTURE_MARGIN, FIXTURE_KYC, FIXTURE_CYBER]


def write_fixture_pdf(fixture: FixtureCircular, directory: Path) -> Path:
    """Render a fixture to a real PDF with a genuine embedded text layer."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{fixture.circular_number.replace('/', '_')}.pdf"

    doc = pymupdf.open()
    for page_text in fixture.pages:
        page = doc.new_page()
        page.insert_textbox(
            pymupdf.Rect(56, 56, 556, 736), page_text, fontsize=11, fontname="helv"
        )
    doc.save(str(path))
    doc.close()
    return path


def write_scanned_pdf(directory: Path, name: str = "scanned.pdf") -> Path:
    """A page with no meaningful text layer — exercises the vision branch."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    doc = pymupdf.open()
    page = doc.new_page()
    # A few drawn lines and nothing else: near-zero extractable characters.
    page.draw_rect(pymupdf.Rect(80, 80, 500, 300))
    page.draw_line(pymupdf.Point(80, 200), pymupdf.Point(500, 200))
    doc.save(str(path))
    doc.close()
    return path
