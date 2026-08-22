"""Parse and index a policy pack markdown file into clauses.

Clause offsets index into the pack's markdown source, exactly as circular
offsets index into ``circulars.full_text``. A finding's ``clause_span`` is
therefore resolvable the same way its ``circular_span`` is, and the
side-by-side evidence pane can highlight both from the same primitive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.policy import PolicyClause, PolicyPack
from app.repositories.policy import PolicyRepository

log = get_logger("app.services.policy_pack")

# "### A.1 Client due diligence before activation"
_CLAUSE_HEADING = re.compile(r"^###\s+([A-Z]\.\d+)\s+(.+?)\s*$", re.MULTILINE)
# "## Part A — Client Onboarding and KYC"
_PART_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ParsedClause:
    order_index: int
    clause_number: str
    heading: str
    heading_path: str
    text: str
    char_start: int
    char_end: int


def parse_pack(markdown: str) -> list[ParsedClause]:
    """Split a policy pack into numbered clauses with source offsets.

    A clause runs from its ``###`` heading to the next heading of any level,
    so the stored text includes the clause body but not the following clause.
    """
    parts = [(m.start(), m.group(1).strip()) for m in _PART_HEADING.finditer(markdown)]

    def part_for(position: int) -> str:
        current = ""
        for start, title in parts:
            if start < position:
                current = title
            else:
                break
        return current

    clauses: list[ParsedClause] = []
    matches = list(_CLAUSE_HEADING.finditer(markdown))

    for index, match in enumerate(matches):
        start = match.start()
        # The clause ends where the next heading of any level begins.
        next_heading = markdown.find("\n#", match.end())
        end = next_heading if next_heading != -1 else len(markdown)
        # Trim trailing horizontal rules and whitespace without moving `start`.
        text = markdown[start:end].rstrip()
        text = re.sub(r"\n+---\s*$", "", text).rstrip()
        end = start + len(text)

        clauses.append(
            ParsedClause(
                order_index=index,
                clause_number=match.group(1),
                heading=match.group(2),
                heading_path=part_for(start),
                text=text,
                char_start=start,
                char_end=end,
            )
        )
    return clauses


async def index_pack(
    session: AsyncSession,
    path: Path,
    *,
    name: str,
    version: str,
    description: str | None = None,
    is_synthetic: bool = True,
) -> PolicyPack:
    """Parse a pack from disk and store it with its clauses.

    Re-indexing an existing (name, version) is a no-op: the pack is returned
    unchanged so ``make seed`` is safe to re-run.
    """
    repo = PolicyRepository(session)
    existing = await repo.get_pack_by_name(name, version)
    if existing is not None:
        log.info("policy_pack.exists", extra={"name": name, "version": version})
        return existing

    markdown = path.read_text(encoding="utf-8")
    parsed = parse_pack(markdown)
    if not parsed:
        raise ValueError(f"no '### <clause>' headings found in {path}")

    pack = await repo.add_pack(
        PolicyPack(
            name=name,
            version=version,
            description=description,
            source_path=str(path),
            is_synthetic=is_synthetic,
        )
    )
    await repo.add_clauses(
        [
            PolicyClause(
                policy_pack_id=pack.id,
                order_index=clause.order_index,
                clause_number=clause.clause_number,
                heading=clause.heading,
                heading_path=clause.heading_path,
                text=clause.text,
                char_start=clause.char_start,
                char_end=clause.char_end,
            )
            for clause in parsed
        ]
    )
    log.info(
        "policy_pack.indexed",
        extra={"name": name, "version": version, "clauses": len(parsed)},
    )
    return pack
