"""Assessment and finding persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.assessment import Assessment, Finding
from app.db.models.enums import AnalystDecision, AssessmentStatus, ImpactType


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
        stmt = select(Assessment).order_by(Assessment.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars())

    async def set_status(
        self,
        assessment_id: int,
        status: AssessmentStatus,
        *,
        error_reason: str | None = None,
    ) -> None:
        """Terminal statuses stamp ``completed_at``. CAPPED is terminal but not
        a failure — the run halted on a hard limit and keeps its findings."""
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            return
        assessment.status = status
        if error_reason is not None:
            assessment.error_reason = error_reason
        if status in (AssessmentStatus.COMPLETED, AssessmentStatus.FAILED, AssessmentStatus.CAPPED):
            assessment.completed_at = datetime.now(UTC)
        await self.session.flush()

    async def record_usage(self, assessment_id: int, tokens: int, cost_usd: float) -> None:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            return
        assessment.total_tokens += tokens
        assessment.total_cost_usd += cost_usd
        await self.session.flush()

    async def set_memo(self, assessment_id: int, memo: str) -> None:
        assessment = await self.session.get(Assessment, assessment_id)
        if assessment is None:
            return
        assessment.memo = memo
        await self.session.flush()


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
            .order_by(Finding.confidence.desc())
        )
        return list((await self.session.execute(stmt)).scalars())

    async def set_decision(self, finding_id: int, decision: AnalystDecision) -> Finding | None:
        finding = await self.session.get(Finding, finding_id)
        if finding is None:
            return None
        finding.analyst_decision = decision
        await self.session.flush()
        return finding

    async def impact_counts(self, assessment_id: int) -> dict[ImpactType, int]:
        """Findings per impact type — drives the summary strip in the UI."""
        stmt = (
            select(Finding.impact_type, func.count(Finding.id))
            .where(Finding.assessment_id == assessment_id)
            .group_by(Finding.impact_type)
        )
        return {row[0]: int(row[1]) for row in (await self.session.execute(stmt)).all()}
