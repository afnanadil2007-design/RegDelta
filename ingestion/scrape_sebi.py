"""Acquire a small corpus of official SEBI circulars for the research evaluation.

SEBI's listing pages (Legal > Circulars, Legal > Master Circulars) give a date
and a title per row and link to a page that embeds the PDF. The circular
number is printed in the PDF, so it is read from the first pages after the
download.

Selection is a rule, not a hand pick: the first listing page of each section
(the most recent 25 documents on the retrieval date), kept when the title
matches RegDelta's domain (market intermediaries: brokers, KYC, positions and
margins, cyber security and IT resilience, investor awareness and grievances,
the exchanges, clearing corporations and depositories brokers work through)
and does not match an excluded topic (issuers, funds, ratings). Later listing
pages are reached only through the site's JavaScript form, which this script
does not drive.

Polite and bounded: an identifying User-Agent, at least two seconds between
requests, GET only. PDFs stay out of git (``data/real_sources/pdf/``); the
manifest records page and PDF URLs, dates, number and SHA-256 so anyone can
re-fetch the same files and verify them.

    python -m ingestion.scrape_sebi --limit 25          # select, download, write the manifest
    python -m ingestion.scrape_sebi --fetch-missing     # re-download what the manifest names
    python -m ingestion.scrape_sebi --verify            # check local files against the manifest
    python -m ingestion.scrape_sebi --reindex           # re-read numbers from the local PDFs
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ingestion.manifest import ManifestEntry, corpus_paths, read_manifest, write_manifest

_PATHS = corpus_paths("real")  # the scraper never writes the synthetic corpus
DATA_DIR = _PATHS.pdf_dir
MANIFEST_PATH = _PATHS.manifest

SEBI_BASE = "https://www.sebi.gov.in"
LISTINGS = {
    "circular": "/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0",
    "master_circular": "/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0",
}
USER_AGENT = "RegDelta/0.1 (regulatory change-impact research; see repository README)"
MIN_DELAY = 2.0

INCLUDE = (
    "stock broker",
    "kyc",
    "position limit",
    "margin",
    "cyber",
    "it resilience",
    "investor awareness",
    "grievance",
    "depositor",
    "stock exchanges and clearing",
    "surveillance",
    "investment advisers",
    "research analysts",
    "portfolio managers",
    "registrars to an issue",
    "digital accessibility",
)
EXCLUDE = (
    "debt securit",
    "debenture",
    "mutual fund",
    "alternative investment",
    "aif",
    "invit",
    "reit",
    "fpi",
    "angel fund",
    "rating",
    "municipal",
    "listing obligations",
    "issue of capital",
    "social stock exchange",
    "merchant banker",
)

_ROW = re.compile(
    r"<td>(?P<date>[A-Z][a-z]{2} \d{2}, \d{4})</td>\s*<td><a href=\"(?P<href>[^\"]+)\"[^>]*"
    r"title=\"(?P<title>[^\"]+)\"",
)
_PDF = re.compile(r"""(?:\?file=)?(https?://www\.sebi\.gov\.in/sebi_data/[^"'\s<>]+?\.pdf)""")
# Old style SEBI/HO/MIRSD/... and the 2026 styles HO/38/14/(4)2026-MIRSD-POD/I/...
# and HO/(449)2026-ITD-5_DIV1/I/....
_NUMBER = re.compile(r"((?:SEBI/)?HO/\(?[A-Za-z0-9]+[A-Za-z0-9_/\-()]*[A-Za-z0-9)])")


@dataclass
class Row:
    kind: str
    issued: date
    title: str
    page_url: str


def selected(title: str) -> bool:
    lowered = title.lower()
    return any(word in lowered for word in INCLUDE) and not any(w in lowered for w in EXCLUDE)


def parse_listing(text: str, kind: str) -> list[Row]:
    rows = []
    for match in _ROW.finditer(text):
        rows.append(
            Row(
                kind=kind,
                issued=datetime.strptime(match.group("date"), "%b %d, %Y").date(),
                title=html.unescape(match.group("title")).strip(),
                page_url=match.group("href"),
            )
        )
    return rows


def pdf_url(page: str, page_url: str) -> str | None:
    match = _PDF.search(page)
    if match:
        return match.group(1)
    for href in re.findall(r"href=\"([^\"]+\.pdf)\"", page):
        url = urljoin(page_url, href)
        query = parse_qs(urlparse(url).query).get("file")
        return query[0] if query else url
    return None


def circular_number(pdf: bytes) -> str | None:
    """The number printed near the top of the first pages, or None (e.g. a scan)."""
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as document:
        text = " ".join(document[i].get_text() for i in range(min(2, document.page_count)))
    # PDF text breaks long numbers after a slash: "MRD-POD1/ I/20735/2026".
    text = re.sub(r"/\s+", "/", text)
    match = _NUMBER.search(text)
    return match.group(1).rstrip("/") if match else None


def _filename(number: str | None, page_url: str) -> str:
    if number:
        return re.sub(r"[^A-Za-z0-9_\-]+", "_", number).strip("_") + ".pdf"
    return "sebi_" + Path(urlparse(page_url).path).stem.rsplit("_", 1)[-1] + ".pdf"


class Polite:
    """An HTTP client that never sends two requests closer than ``delay``."""

    def __init__(self, delay: float) -> None:
        self.delay = max(delay, MIN_DELAY)
        self.last = 0.0
        self.client = httpx.Client(
            base_url=SEBI_BASE,
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
        )

    def get(self, url: str) -> httpx.Response:
        wait = self.last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            response = self.client.get(url)
        finally:
            self.last = time.monotonic()
        response.raise_for_status()
        return response

    def close(self) -> None:
        self.client.close()


def acquire(limit: int, delay: float) -> int:
    client = Polite(delay)
    today = date.today().isoformat()
    entries: list[ManifestEntry] = []
    try:
        candidates: list[Row] = []
        for kind, path in LISTINGS.items():
            rows = parse_listing(client.get(path).text, kind)
            kept = [r for r in rows if selected(r.title)]
            print(f"{kind}: {len(rows)} listed, {len(kept)} match the domain rule")
            candidates += kept
        candidates.sort(key=lambda r: r.issued, reverse=True)

        for row in candidates[:limit]:
            try:
                page = client.get(row.page_url).text
                url = pdf_url(page, row.page_url)
                if url is None:
                    print(f"  ! no PDF on {row.page_url}", file=sys.stderr)
                    continue
                pdf = client.get(url).content
            except httpx.HTTPError as exc:
                print(f"  ! {row.title[:60]}: {exc}", file=sys.stderr)
                continue
            if not pdf.startswith(b"%PDF"):
                print(f"  ! {row.title[:60]}: response was not a PDF", file=sys.stderr)
                continue
            number = circular_number(pdf)
            filename = _filename(number, row.page_url)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / filename).write_bytes(pdf)
            entries.append(
                ManifestEntry(
                    circular_number=number or filename.removesuffix(".pdf"),
                    title=row.title,
                    issue_date=row.issued.isoformat(),
                    department=None,
                    doc_type=row.kind,
                    source_url=url,
                    pdf_filename=filename,
                    page_url=row.page_url,
                    retrieved_on=today,
                    sha256=hashlib.sha256(pdf).hexdigest(),
                    note=(
                        "Official SEBI publication. Not redistributed in this repository; "
                        "fetch it from source_url."
                        + ("" if number else " Circular number not found in the first pages.")
                    ),
                )
            )
            print(f"  + {row.issued} {filename} ({len(pdf) // 1024} KiB)")
    finally:
        client.close()
    write_manifest(entries, MANIFEST_PATH)
    print(f"{len(entries)} documents; manifest {MANIFEST_PATH}")
    return 0 if entries else 1


def reindex() -> int:
    """Re-read circular numbers from the local PDFs and rename them to match."""
    entries = read_manifest(MANIFEST_PATH)
    for entry in entries:
        path = DATA_DIR / entry.pdf_filename
        if not path.is_file():
            continue
        number = circular_number(path.read_bytes())
        filename = _filename(number, entry.page_url or entry.source_url)
        if filename != entry.pdf_filename:
            path.rename(DATA_DIR / filename)
            print(f"  {entry.pdf_filename} -> {filename}")
        entry.pdf_filename = filename
        entry.circular_number = number or filename.removesuffix(".pdf")
        if number is None and entry.note and "not found" not in entry.note:
            entry.note += " Circular number not found in the first pages (no text layer)."
    write_manifest(entries, MANIFEST_PATH)
    return verify()


def fetch_missing(delay: float) -> int:
    entries = read_manifest(MANIFEST_PATH)
    missing = [e for e in entries if not (DATA_DIR / e.pdf_filename).exists()]
    print(f"{len(entries)} in manifest, {len(missing)} missing locally.")
    client = Polite(delay)
    try:
        for entry in missing:
            pdf = client.get(entry.source_url).content
            (DATA_DIR / entry.pdf_filename).parent.mkdir(parents=True, exist_ok=True)
            (DATA_DIR / entry.pdf_filename).write_bytes(pdf)
    finally:
        client.close()
    return verify()


def verify() -> int:
    """Every manifest entry present locally with its recorded checksum."""
    entries = read_manifest(MANIFEST_PATH)
    bad = 0
    for entry in entries:
        path = DATA_DIR / entry.pdf_filename
        if not path.is_file():
            print(f"  missing  {entry.pdf_filename}")
            bad += 1
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry.sha256:
            print(f"  changed  {entry.pdf_filename} (the source may have been revised)")
            bad += 1
    print(f"{len(entries) - bad} of {len(entries)} verified.")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire official SEBI circulars.")
    parser.add_argument("--limit", type=int, default=25, help="documents to keep at most")
    parser.add_argument("--delay", type=float, default=MIN_DELAY, help="seconds between requests")
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--reindex", action="store_true", help="re-read numbers from local PDFs")
    args = parser.parse_args(argv)
    if args.delay < MIN_DELAY:
        parser.error(f"--delay must be at least {MIN_DELAY} seconds")
    if args.verify:
        return verify()
    if args.reindex:
        return reindex()
    if args.fetch_missing:
        return fetch_missing(args.delay)
    return acquire(args.limit, args.delay)


if __name__ == "__main__":
    raise SystemExit(main())
