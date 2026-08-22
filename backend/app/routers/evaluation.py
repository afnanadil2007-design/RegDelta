"""Evaluation dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.evaluation import EvaluationRepository
from app.routers.schemas import EvalMetricOut, EvalRunOut

router = APIRouter(tags=["evaluation"])


@router.get("/eval/runs", response_model=list[EvalRunOut])
async def list_runs(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[EvalRunOut]:
    repo = EvaluationRepository(session)
    runs = await repo.list_runs(limit=limit)
    out: list[EvalRunOut] = []
    for run in runs:
        results = await repo.list_results(run.id)
        out.append(
            EvalRunOut(
                id=run.id,
                suite=run.suite.value,
                mode=run.mode.value if run.mode else None,
                git_sha=run.git_sha,
                dataset=run.dataset,
                started_at=run.started_at,
                finished_at=run.finished_at,
                results=[
                    EvalMetricOut(
                        metric_name=r.metric_name,
                        metric_value=r.metric_value,
                        subset=r.subset,
                        k=r.k,
                    )
                    for r in results
                ],
            )
        )
    return out
