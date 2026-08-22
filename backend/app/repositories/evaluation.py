"""Evaluation run and result persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import EvalSuite, RetrievalMode
from app.db.models.evaluation import EvalResult, EvalRun


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_run(self, run: EvalRun) -> EvalRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def finish_run(self, run_pk: int) -> None:
        run = await self.session.get(EvalRun, run_pk)
        if run is None:
            return
        run.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def add_results(self, results: list[EvalResult]) -> list[EvalResult]:
        self.session.add_all(results)
        await self.session.flush()
        return results

    async def list_runs(self, suite: EvalSuite | None = None, limit: int = 50) -> list[EvalRun]:
        stmt = select(EvalRun).order_by(EvalRun.started_at.desc()).limit(limit)
        if suite:
            stmt = stmt.where(EvalRun.suite == suite)
        return list((await self.session.execute(stmt)).scalars())

    async def list_results(self, run_pk: int) -> list[EvalResult]:
        stmt = select(EvalResult).where(EvalResult.eval_run_id == run_pk).order_by(EvalResult.id)
        return list((await self.session.execute(stmt)).scalars())

    async def latest_run(
        self, suite: EvalSuite, mode: RetrievalMode | None = None
    ) -> EvalRun | None:
        """Most recent completed run, used to render the current ablation table."""
        stmt = (
            select(EvalRun)
            .where(EvalRun.suite == suite, EvalRun.finished_at.is_not(None))
            .order_by(EvalRun.finished_at.desc())
            .limit(1)
        )
        if mode is not None:
            stmt = stmt.where(EvalRun.mode == mode)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def metric_history(self, metric_name: str, limit: int = 30) -> list[tuple[str, float]]:
        """(git_sha, value) over time — the trend chart on the eval dashboard."""
        stmt = (
            select(EvalRun.git_sha, EvalResult.metric_value)
            .join(EvalResult, EvalResult.eval_run_id == EvalRun.id)
            .where(EvalResult.metric_name == metric_name)
            .order_by(EvalRun.started_at.desc())
            .limit(limit)
        )
        return [(r[0], float(r[1])) for r in (await self.session.execute(stmt)).all()]
