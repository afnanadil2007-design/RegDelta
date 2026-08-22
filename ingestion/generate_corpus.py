"""Generate a deterministic SYNTHETIC SEBI-style corpus.

WHY THIS EXISTS
---------------
``scrape_sebi.py`` targets the real sebi.gov.in listing, but the site renders
circular detail pages client-side: the listing HTML yields links, and each
detail page returns a JavaScript shell with no reference number, date, or PDF
link in the markup. Fetching the real corpus therefore needs a headless
browser, which is a dependency this project deliberately does not take.

So development and evaluation run on a synthetic corpus generated here. It is
*structurally* faithful — real reference-number families, a dense
cross-citation graph, supersession chains, and obligation language drawn from
the same domains as the policy pack — which is what the retrieval, citation,
and extraction code paths actually exercise. It is not, and does not claim to
be, real regulation.

EVERY metric measured against this corpus must be reported as measured on
synthetic data. See docs/decisions/0003-citation-graph-gold-set.md.

The generator is seeded, so the corpus (and therefore every evaluation number)
is reproducible from the seed alone.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pymupdf

from ingestion.manifest import DATA_DIR, MANIFEST_PATH, ManifestEntry, write_manifest

SEED = 20240101
SYNTHETIC_BANNER = "[SYNTHETIC CORPUS — NOT A REAL SEBI CIRCULAR]"

DEPARTMENTS = {
    "MIRSD": "Market Intermediaries Regulation and Supervision Department",
    "CFD": "Corporation Finance Department",
    "MRD": "Market Regulation Department",
    "IMD": "Investment Management Department",
    "ITD": "Information Technology Department",
    "OIAE": "Office of Investor Assistance and Education",
    "ISD": "Integrated Surveillance Department",
    "DDHS": "Debt and Hybrid Securities Department",
}


@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    heading: str
    obligations: list[str]


# Topics deliberately mirror the policy pack's domains so assessments have
# genuine matches, conflicts, and near-misses to find.
TOPICS: list[Topic] = [
    Topic(
        "kyc",
        "Client onboarding and KYC verification norms",
        "CLIENT ONBOARDING AND KYC",
        [
            "Intermediaries shall complete client due diligence before activating a trading account.",
            "Intermediaries shall verify the Permanent Account Number of every client against the income tax database at the time of onboarding.",
            "In-person verification shall be completed within {n} days of account opening.",
            "Intermediaries shall obtain a self-attested proof of address and retain it with the client file.",
            "Re-KYC shall be carried out at least once every {n} years for clients categorised as low risk.",
        ],
    ),
    Topic(
        "margin",
        "Upfront collection of margins from clients",
        "UPFRONT COLLECTION OF MARGINS",
        [
            "Stock brokers shall collect upfront margin from clients before accepting orders in the cash and derivatives segments.",
            "Stock brokers shall report instances of short-collection of margin to the Stock Exchange by T+{n} day.",
            "The margin shall be collected in the form of cash, cash equivalents or approved securities held as collateral.",
            "Penalty for short collection shall be levied at {n} percent of the shortfall amount.",
            "Stock brokers shall retain evidence of margin collection for a period of {n} years.",
        ],
    ),
    Topic(
        "order",
        "Order handling and best execution obligations",
        "ORDER HANDLING AND EXECUTION",
        [
            "Stock brokers shall time-stamp every client order at the point of receipt.",
            "Stock brokers shall maintain an audit trail of order modifications and cancellations for {n} years.",
            "Orders shall be executed in the sequence in which they are received unless the client directs otherwise.",
            "Stock brokers shall not aggregate client orders with proprietary orders without written consent.",
        ],
    ),
    Topic(
        "risk",
        "Risk disclosure to clients",
        "RISK DISCLOSURE REQUIREMENTS",
        [
            "Stock brokers shall furnish a risk disclosure document to every client prior to the first trade.",
            "The risk disclosure document shall be acknowledged by the client in writing or electronically.",
            "Brokers shall display the prescribed risk disclosure prominently on their trading interface.",
            "Risk disclosures shall be reviewed and updated at least once every {n} years.",
        ],
    ),
    Topic(
        "grievance",
        "Investor grievance redressal mechanism",
        "INVESTOR GRIEVANCE REDRESSAL",
        [
            "Intermediaries shall resolve investor complaints within {n} days of receipt.",
            "Intermediaries shall designate a compliance officer responsible for grievance redressal.",
            "A monthly report of pending complaints shall be submitted to the Stock Exchange.",
            "Intermediaries shall register on the SCORES platform and respond to complaints through it.",
        ],
    ),
    Topic(
        "retention",
        "Maintenance and retention of records",
        "RECORD MAINTENANCE AND RETENTION",
        [
            "Intermediaries shall preserve books of account and records for a minimum period of {n} years.",
            "Records relating to a matter under investigation shall be preserved until the proceedings conclude.",
            "Electronic records shall be maintained in a tamper-evident and readily retrievable form.",
            "Intermediaries shall produce records during inspection within {n} working days of a request.",
        ],
    ),
    Topic(
        "cyber",
        "Cyber security and cyber resilience framework",
        "CYBER SECURITY AND CYBER RESILIENCE",
        [
            "Intermediaries shall establish a documented cyber security policy approved by the governing board.",
            "Intermediaries shall report cyber security incidents to SEBI within {n} hours of detection.",
            "A Vulnerability Assessment and Penetration Test shall be conducted at least once every financial year.",
            "Intermediaries shall appoint a Chief Information Security Officer responsible for the framework.",
            "Critical systems shall be subjected to a disaster recovery drill every {n} months.",
        ],
    ),
    Topic(
        "reporting",
        "Periodic reporting and regulatory filings",
        "PERIODIC REPORTING OBLIGATIONS",
        [
            "Intermediaries shall submit a half-yearly internal audit report to the Stock Exchange.",
            "The compliance certificate shall be filed within {n} days of the end of each quarter.",
            "Any change in control shall be intimated to SEBI within {n} days.",
            "Intermediaries shall file an annual system audit report conducted by a CERT-In empanelled auditor.",
        ],
    ),
]


def _reference(dept: str, year: int, serial: int, style: int) -> str:
    """A reference number in one of the families the regex must handle."""
    if style == 0:
        return f"SEBI/HO/{dept}/{dept}-PoD-{1 + serial % 3}/P/CIR/{year}/{serial}"
    if style == 1:
        return f"SEBI/HO/{dept}/CIR/P/{year}/{serial}"
    return f"SEBI/HO/{dept}/{dept}_Div{1 + serial % 2}/P/CIR/{year}/{serial}"


@dataclass
class GeneratedCircular:
    number: str
    title: str
    issue_date: date
    department: str
    topic: Topic
    pages: list[str]


# Citing paragraphs must carry the *subject matter* of the circular they cite.
# Real circulars cite by topic ("the margin collection requirements specified
# in X"), and the semantic gold subset is built from these paragraphs — a
# boilerplate "read together with X" sentence would make that subset
# unanswerable by any retriever and the evaluation meaningless.
_CITE_TEMPLATES = [
    "The requirements relating to {subject}, issued in {year} by the {dept}, "
    "are specified in {ref} and shall continue to apply.",
    "This circular supplements the {year} provisions on {subject} issued by the {dept} vide {ref}.",
    "Intermediaries shall read this circular together with the {subject} framework "
    "laid down by the {dept} in {year} vide {ref}.",
    "Nothing in this circular dilutes the obligations concerning {subject} under the "
    "{dept} circular of {year}, {ref}.",
]


def _body(
    rng: random.Random,
    topic: Topic,
    cites: list[tuple[str, str, int, str]],
    supersedes: str | None,
    supersede_subject: str | None,
    supersede_date: date | None,
) -> list[str]:
    """Compose the circular text, including citation and supersession language.

    ``cites`` is a list of (reference, subject, year, department) so each
    citing sentence can identify what the cited circular is about.
    """
    lines: list[str] = []
    n = 1
    for template in topic.obligations:
        lines.append(f"{n}. " + template.format(n=rng.choice([1, 2, 3, 5, 6, 7, 15, 21, 30])))
        n += 1

    for ref, subject, year, dept in cites:
        template = rng.choice(_CITE_TEMPLATES)
        lines.append(f"{n}. " + template.format(subject=subject, ref=ref, year=year, dept=dept))
        n += 1

    if supersedes and supersede_date:
        lines.append(
            f"{n}. The provisions relating to {supersede_subject} contained in "
            f"{supersedes} dated {supersede_date.strftime('%B %d, %Y')} shall "
            f"stand superseded from the date of this circular."
        )
        n += 1

    lines.append(
        f"{n}. This circular is issued in exercise of powers conferred under "
        f"Section 11(1) of the Securities and Exchange Board of India Act, 1992."
    )
    return lines


def generate(count: int, seed: int = SEED) -> list[GeneratedCircular]:
    rng = random.Random(seed)
    circulars: list[GeneratedCircular] = []
    start = date(2019, 1, 7)

    for i in range(count):
        topic = TOPICS[i % len(TOPICS)]
        dept = list(DEPARTMENTS)[i % len(DEPARTMENTS)]
        issued = start + timedelta(days=int(i * (365 * 6 / max(count, 1))) + rng.randint(0, 5))
        number = _reference(dept, issued.year, 10 + i, style=i % 3)

        # Cite two earlier circulars. Mixing same-topic and cross-topic
        # citations keeps the semantic subset from being solvable by topic
        # alone while still carrying genuine signal.
        same_topic = [c for c in circulars if c.topic is topic]
        pool = same_topic or circulars
        chosen = rng.sample(pool, min(2, len(pool))) if pool else []
        cites = [
            (c.number, c.topic.title.lower(), c.issue_date.year, DEPARTMENTS[c.department])
            for c in chosen
        ]

        # Roughly every fourth circular supersedes an earlier one on its topic.
        supersedes, supersede_subject, supersede_date = None, None, None
        if same_topic and i % 4 == 0:
            victim = rng.choice(same_topic)
            supersedes = victim.number
            supersede_subject = victim.topic.title.lower()
            supersede_date = victim.issue_date

        header = [
            SYNTHETIC_BANNER,
            "",
            number,
            "",
            issued.strftime("%B %d, %Y"),
            "",
            "To",
            "All Registered Intermediaries",
            "",
            topic.heading,
            "",
        ]
        body = _body(rng, topic, cites, supersedes, supersede_subject, supersede_date)

        # Split across two pages once the body is long enough, so multi-page
        # extraction and cross-page paragraph ordering are exercised.
        if len(body) > 6:
            pages = ["\n\n".join(header + body[:5]), "\n\n".join(body[5:])]
        else:
            pages = ["\n\n".join(header + body)]

        circulars.append(
            GeneratedCircular(
                number=number,
                title=f"{topic.title} ({issued.year})",
                issue_date=issued,
                department=dept,
                topic=topic,
                pages=pages,
            )
        )
    return circulars


def write_pdf(circular: GeneratedCircular, directory: Path) -> Path:
    path = directory / (circular.number.replace("/", "_") + ".pdf")
    doc = pymupdf.open()
    for text in circular.pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 562, 742), text, fontsize=10.5, fontname="helv")
    doc.save(str(path))
    doc.close()
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    circulars = generate(args.count, args.seed)

    entries: list[ManifestEntry] = []
    for circular in circulars:
        path = write_pdf(circular, DATA_DIR)
        entries.append(
            ManifestEntry(
                circular_number=circular.number,
                title=circular.title,
                issue_date=circular.issue_date.isoformat(),
                department=circular.department,
                doc_type="circular",
                source_url=f"synthetic://regdelta/{path.name}",
                pdf_filename=path.name,
            )
        )
    write_manifest(entries, MANIFEST_PATH)

    print(f"Generated {len(entries)} SYNTHETIC circulars in {DATA_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    print("These are NOT real SEBI circulars — see the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
