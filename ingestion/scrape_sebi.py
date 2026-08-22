"""Fetch SEBI circular metadata and PDFs from sebi.gov.in.

Politeness is not optional here: a fixed delay of at least
``SCRAPE_DELAY_SECONDS`` (default 2s) separates every request, requests are
made with an identifying User-Agent, and the date range is explicit so a run
fetches a bounded slice rather than crawling the whole site.

Usage:
    python -m ingestion.scrape_sebi --from 2023-01-01 --to 2024-12-31
    python -m ingestion.scrape_sebi --manifest-only     # metadata, no PDFs
    python -m ingestion.scrape_sebi --fetch-missing     # PDFs named by the manifest
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx

from ingestion.manifest import (
    DATA_DIR,
    MANIFEST_PATH,
    ManifestEntry,
    read_manifest,
    write_manifest,
)

SEBI_BASE = "https://www.sebi.gov.in"
LISTING_PATH = "/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0"

USER_AGENT = "RegDelta/0.1 (regulatory change-impact research; contact: see repository README)"

# Department code inside a SEBI reference, e.g. .../HO/MIRSD/... -> MIRSD.
_DEPARTMENT = re.compile(r"SEBI/HO/([A-Z]+)/")


def department_of(circular_number: str) -> str | None:
    match = _DEPARTMENT.search(circular_number)
    return match.group(1) if match else None


def _client(delay: float) -> httpx.Client:
    return httpx.Client(
        base_url=SEBI_BASE,
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )


def fetch_pdf(client: httpx.Client, entry: ManifestEntry, delay: float) -> Path | None:
    """Download one PDF. Returns None on failure — never aborts the run."""
    target = DATA_DIR / entry.pdf_filename
    if target.exists():
        return target

    time.sleep(delay)
    try:
        response = client.get(entry.source_url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  ! {entry.circular_number}: {exc}", file=sys.stderr)
        return None

    if not response.content.startswith(b"%PDF"):
        print(f"  ! {entry.circular_number}: response was not a PDF", file=sys.stderr)
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    print(f"  + {entry.circular_number} -> {target.name}")
    return target


def fetch_missing(delay: float) -> int:
    """Fetch every PDF named by the manifest that is not already on disk."""
    entries = read_manifest(MANIFEST_PATH)
    if not entries:
        print(f"No manifest at {MANIFEST_PATH}. Run with --from/--to first.")
        return 1

    missing = [e for e in entries if not (DATA_DIR / e.pdf_filename).exists()]
    print(f"{len(entries)} in manifest, {len(missing)} missing locally.")

    with _client(delay) as client:
        fetched = sum(1 for e in missing if fetch_pdf(client, e, delay) is not None)
    print(f"Fetched {fetched}/{len(missing)}.")
    return 0


def scrape_listing(
    client: httpx.Client, date_from: date, date_to: date, delay: float
) -> list[ManifestEntry]:
    """Collect circular metadata for the date range.

    SEBI's listing is a server-rendered, paginated form. This walks pages until
    it runs out of rows in range, sleeping ``delay`` between requests.
    """
    entries: list[ManifestEntry] = []
    page = 1
    while True:
        time.sleep(delay)
        response = client.get(LISTING_PATH, params={"nextValue": page})
        response.raise_for_status()

        rows = _parse_listing(response.text)
        if not rows:
            break

        in_range = [r for r in rows if r[2] and date_from <= r[2] <= date_to]
        for number, title, issued, href in in_range:
            entries.append(
                ManifestEntry(
                    circular_number=number,
                    title=title,
                    issue_date=issued.isoformat() if issued else None,
                    department=department_of(number),
                    doc_type="circular",
                    source_url=href if href.startswith("http") else SEBI_BASE + href,
                    pdf_filename=number.replace("/", "_") + ".pdf",
                )
            )

        # Rows are newest-first; stop once the page is entirely older than the range.
        if rows and all(r[2] and r[2] < date_from for r in rows):
            break
        page += 1

    return entries


_ROW = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>[^<]+)</a>.*?'
    r"(?P<date>\w+ \d{1,2}, \d{4}).*?"
    r"(?P<number>SEBI/[A-Z0-9/\-]+)",
    re.DOTALL | re.IGNORECASE,
)


def _parse_listing(html: str) -> list[tuple[str, str, date | None, str]]:
    """Extract (number, title, date, href) tuples from a listing page.

    SEBI's markup changes periodically; a parse that yields nothing is treated
    as "end of results" by the caller rather than crashing the run.
    """
    rows: list[tuple[str, str, date | None, str]] = []
    for match in _ROW.finditer(html):
        try:
            issued = datetime.strptime(match.group("date"), "%B %d, %Y").date()
        except ValueError:
            issued = None
        rows.append(
            (
                match.group("number").strip(),
                match.group("title").strip(),
                issued,
                match.group("href").strip(),
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch SEBI circulars.")
    parser.add_argument("--from", dest="date_from", default="2023-01-01")
    parser.add_argument("--to", dest="date_to", default=date.today().isoformat())
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    parser.add_argument("--manifest-only", action="store_true", help="skip PDF download")
    parser.add_argument(
        "--fetch-missing", action="store_true", help="download PDFs the manifest names"
    )
    args = parser.parse_args(argv)

    if args.delay < 2.0:
        parser.error("--delay must be at least 2.0 seconds (be polite to sebi.gov.in)")

    if args.fetch_missing:
        return fetch_missing(args.delay)

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)
    print(f"Scraping SEBI circulars {date_from} .. {date_to} (delay {args.delay}s)")

    with _client(args.delay) as client:
        entries = scrape_listing(client, date_from, date_to, args.delay)
        print(f"Found {len(entries)} circulars.")
        write_manifest(entries, MANIFEST_PATH)
        print(f"Manifest written to {MANIFEST_PATH}")

        if not args.manifest_only:
            fetched = sum(1 for e in entries if fetch_pdf(client, e, args.delay) is not None)
            print(f"Fetched {fetched}/{len(entries)} PDFs into {DATA_DIR}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
