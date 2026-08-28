"""分析任务/风险项/报告/人工复核 路由。

路径兼容两套写法：
  - 现行前端：/analysis/tasks/...、/analysis/risk-findings/...、/analysis/review-reports/...
  - 需求 2.7.11 规格：/analysis-tasks/...、/risk-findings/...、/review-reports/...
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser
from ..database import get_db
from ..models import AnalysisTask, RiskFinding, ReviewReport
from ..schemas.analysis import FindingReviewIn
from ..schemas.approval import ManualReviewIn
from ..services import analysis_service
from ..services.report_service import (
    add_manual_review, get_report, get_report_by_task, report_to_dict, update_finding_status,
)

router = APIRouter(tags=["analysis"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/analysis/tasks/{task_id}")
@router.get("/analysis-tasks/{task_id}")
async def get_task(task_id: int, db: DbDep, user: CurrentUser):
    task = (await db.execute(select(AnalysisTask).where(
        AnalysisTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ok({
        "task_id": task.id, "task_status": task.task_status, "current_step": task.current_step,
        "progress": task.progress, "document_id": task.document_id,
        "finished_at": task.finished_at, "error_message": task.error_message,
    })


@router.get("/analysis/tasks/{task_id}/findings")
@router.get("/analysis-tasks/{task_id}/findings")
async def get_findings(task_id: int, db: DbDep, user: CurrentUser):
    findings = (await db.execute(select(RiskFinding).where(
        RiskFinding.task_id == task_id))).scalars().all()
    return ok(analysis_service.findings_to_out(findings))


@router.get("/analysis/tasks/{task_id}/report")
@router.get("/analysis-tasks/{task_id}/report")
async def get_report_by_task_endpoint(task_id: int, db: DbDep, user: CurrentUser):
    report = await get_report_by_task(db, task_id)
    return ok(report_to_dict(report))


# ---- 风险项复核 ----
@router.patch("/analysis/risk-findings/{finding_id}/review-status")
@router.patch("/risk-findings/{finding_id}/review-status")
async def update_review_status(finding_id: int, body: FindingReviewIn, db: DbDep, user: CurrentUser):
    return ok(await update_finding_status(db, user, finding_id, body.review_status))


# ---- 人工复核 ----
@router.post("/analysis/review-reports/{report_id}/manual-reviews")
@router.post("/review-reports/{report_id}/manual-reviews")
async def submit_manual_review(report_id: int, body: ManualReviewIn, db: DbDep, user: CurrentUser):
    result = await add_manual_review(db, user, report_id, body.review_result, body.review_comment)
    return ok(result, "复核已提交")


@router.get("/analysis/review-reports/{report_id}/export")
@router.get("/review-reports/{report_id}/export")
async def export_report(report_id: int, db: DbDep, user: CurrentUser):
    report = await get_report(db, report_id)
    return PlainTextResponse(report.report_markdown, media_type="text/markdown; charset=utf-8")
