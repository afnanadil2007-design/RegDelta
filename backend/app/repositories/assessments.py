"""Assessment and finding persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment, Finding
from app.db.models.corpus import Obligation
from app.db.models.enums import (
    TERMINAL_STATUSES,
    AnalystDecision,
    AssessmentStatus,
    ImpactType,
    QuoteStatus,
)
from app.db.models.policy import PolicyClause

_ACTIVE = (AssessmentStatus.PENDING, AssessmentStatus.RUNNING)


@dataclass(frozen=True)
class FindingContext:
    """A finding with the obligation and clause text its offsets point into."""

    finding: Finding
    circular_id: int
    obligation_text: str
    obligation_char_start: int
    obligation_char_end: int
    clause_number: str | None
    clause_heading: str | None
    clause_text: str | None
    clause_char_start: int | None


@dataclass
class FindingCounts:
    total: int = 0
    assessed_obligations: int = 0
    by_quote_status: dict[QuoteStatus, int] = field(default_factory=dict)
    by_impact: dict[ImpactType, int] = field(default_factory=dict)
    by_decision: dict[AnalystDecision, int] = field(default_factory=dict)


class AssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, assessment: Assessment) -> Assessment:
        self.session.add(assessment)
        await self.session.flush()
        return assessment

    async def get(self, assessment_id: int) -> Assessment | None:
        return await self.session.get(Assessment, assessment_id)

    async def get_by_run_id(self, run_id: uuid.UUID) -> Assessment | None:
        stmt = select(Assessment).where(Assessment.run_id == run_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_assessments(self, *, limit: int = 50, offset: int = 0) -> list[Assessment]:
        stmt = (
            select(Assessment)
            .order_by(Assessment.created_at.desc(), Assessment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def count(self) -> int:
        return int((await self.session.execute(select(func.count(Assessment.id)))).scalar_one())

    async def lock_launch(self, circular_id: int, policy_pack_id: int) -> None:
        """Serialise launches for one (circular, pack) until the transaction ends.

        Two near-simultaneous POSTs (a double click) would otherwise both see
        no active run and both start one.
        """
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:circular, :pack)"),
            {"circular": circular_id, "pack": policy_pack_id},
        )

    async def find_active(
        self, circular_id: int, policy_pack_id: int, as_of: date | None
    ) -> Assessment | None:
        """A PENDING or RUNNING run with the same inputs, if one exists."""
        stmt = select(Assessment).where(
            Assessment.circular_id == circular_id,
            Assessment.policy_pack_id == policy_pack_id,
            Assessment.as_of_date.is_not_distinct_from(as_of),
            Assessment.status.in_(_ACTIVE),
        )
        return (await self.session.execute(stmt.limit(1))).scalar_one_or_none()

    async def set_status(self, assessment_id: int, status: AssessmentStatus) -> None:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            return
        assessment.status = status
        if status in TERMINAL_STATUSES:
            assessment.completed_at = datetime.now(UTC)
        await self.session.flush()

    async def finish(
        self,
        assessment_id: int,
        status: AssessmentStatus,
        *,
        detail: str | None,
        memo: str | None,
        tokens: int,
        cost_usd: float,
        unpriced_calls: int,
        failed_tasks: int,
    ) -> None:
        """Record a run's terminal state and usage in one write."""
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            return
        assessment.status = status
        assessment.error_reason = detail
        assessment.memo = memo
        assessment.total_tokens = tokens
        assessment.total_cost_usd = cost_usd
        assessment.unpriced_calls = unpriced_calls
        assessment.failed_tasks = failed_tasks
        assessment.completed_at = datetime.now(UTC)
        await self.session.flush()

    async def fail_unfinished(self, reason: str) -> list[int]:
        """Mark every PENDING/RUNNING assessment FAILED; return their ids."""
        stmt = (
            update(Assessment)
            .where(Assessment.status.in_(_ACTIVE))
            .values(
                status=AssessmentStatus.FAILED,
                error_reason=reason,
                completed_at=func.now(),
            )
            .returning(Assessment.id)
        )
        return [int(row) for row in (await self.session.execute(stmt)).scalars()]


class FindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_all(self, findings: list[Finding]) -> list[Finding]:
        self.session.add_all(findings)
        await self.session.flush()
        return findings

    async def get(self, finding_id: int) -> Finding | None:
        return await self.session.get(Finding, finding_id)

    async def list_for_assessment(self, assessment_id: int) -> list[Finding]:
        stmt = (
            select(Finding)
            .where(Finding.assessment_id == assessment_id)
            .order_by(Finding.obligation_id, Finding.id)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def list_with_context(self, assessment_id: int) -> list[FindingContext]:
        """Findings in reading order of the circular, with their source text."""
        stmt = (
            select(
                Finding,
                Obligation.circular_id,
                Obligation.text,
                Obligation.char_start,
                Obligation.char_end,
                PolicyClause.clause_number,
                PolicyClause.heading,
                PolicyClause.text,
                PolicyClause.char_start,
            )
            .join(Obligation, Obligation.id == Finding.obligation_id)
            .outerjoin(PolicyClause, PolicyClause.id == Finding.policy_clause_id)
            .where(Finding.assessment_id == assessment_id)
            .order_by(Obligation.char_start, PolicyClause.order_index, Finding.id)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            FindingContext(
                finding=row[0],
                circular_id=row[1],
                obligation_text=row[2],
                obligation_char_start=row[3],
                obligation_char_end=row[4],
                clause_number=row[5],
                clause_heading=row[6],
                clause_text=row[7],
                clause_char_start=row[8],
            )
            for row in rows
        ]

    async def get_with_context(self, finding_id: int) -> FindingContext | None:
        finding = await self.session.get(Finding, finding_id)
        if finding is None:
            return None
        for context in await self.list_with_context(finding.assessment_id):
            if context.finding.id == finding_id:
                return context
        return None

    async def set_decision(self, finding_id: int, decision: AnalystDecision) -> Finding | None:
        finding = await self.session.get(Finding, finding_id)
        if finding is None:
            return None
        finding.analyst_decision = decision
        finding.decided_at = None if decision is AnalystDecision.PENDING else datetime.now(UTC)
        await self.session.flush()
        return finding

    async def counts(self, assessment_ids: list[int]) -> dict[int, FindingCounts]:
        """Per-assessment finding tallies, in three grouped queries."""
        out = {aid: FindingCounts() for aid in assessment_ids}
        if not assessment_ids:
            return out

        for column, attribute in (
            (Finding.quote_status, "by_quote_status"),
            (Finding.impact_type, "by_impact"),
            (Finding.analyst_decision, "by_decision"),
        ):
            stmt = (
                select(Finding.assessment_id, column, func.count(Finding.id))
                .where(Finding.assessment_id.in_(assessment_ids))
                .group_by(Finding.assessment_id, column)
            )
            for assessment_id, value, count in (await self.session.execute(stmt)).all():
                getattr(out[assessment_id], attribute)[value] = int(count)

        totals = (
            select(
                Finding.assessment_id,
                func.count(Finding.id),
                func.count(func.distinct(Finding.obligation_id)),
            )
            .where(Finding.assessment_id.in_(assessment_ids))
            .group_by(Finding.assessment_id)
        )
        for assessment_id, total, obligations in (await self.session.execute(totals)).all():
            out[assessment_id].total = int(total)
            out[assessment_id].assessed_obligations = int(obligations)
        return out
