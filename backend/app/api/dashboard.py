"""审核工作台统计与操作日志查询。"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser, resolve_document_scope
from ..database import get_db
from ..models import (
    AnalysisTask, ApprovalTask, AuditLog, DocumentStatusLog, FinancialDocument,
    ReviewReport, RiskFinding,
)

router = APIRouter(tags=["dashboard"])
DbDep = Annotated[AsyncSession, Depends(get_db)]

LEVEL_RANK = {"low": 1, "medium": 2, "high": 3}


@router.get("/dashboard/stats", response_model=dict)
async def dashboard_stats(db: DbDep, user: CurrentUser):
    scope = await resolve_document_scope(user)
    conditions = [] if scope.can_view_all else [FinancialDocument.applicant_id == user.id]

    def scoped():
        base = select(FinancialDocument)
        for c in conditions:
            base = base.where(c)
        return base

    pending_docs = (await db.execute(scoped().where(
        FinancialDocument.document_status.in_(["pending_review", "reviewing"])
    ))).scalars().all()

    # 单据类型分布
    type_rows = (await db.execute(
        select(FinancialDocument.document_type, func.count()).where(*conditions)
        .group_by(FinancialDocument.document_type)
    )).all()
    type_dist = {t: c for t, c in type_rows}

    # 最近分析任务
    recent_tasks = (await db.execute(select(AnalysisTask)
                                     .order_by(AnalysisTask.id.desc()).limit(8))).scalars().all()

    # 待人工复核事项（风险项 pending 数量）
    pending_findings = (await db.execute(select(RiskFinding).where(
        RiskFinding.review_status == "pending"))).scalars().all()
    risk_high, risk_medium, risk_low = 0, 0, 0
    for f in pending_findings:
        if f.risk_level == "high":
            risk_high += 1
        elif f.risk_level == "medium":
            risk_medium += 1
        else:
            risk_low += 1

    # 待审批任务数（当前用户角色）
    from ..services.approval_service import list_my_tasks
    my_tasks = await list_my_tasks(db, user, "pending")

    return ok({
        "pending_documents": len(pending_docs),
        "pending_approval_tasks": len(my_tasks),
        "risk_counts": {"high": risk_high, "medium": risk_medium, "low": risk_low},
        "document_type_distribution": type_dist,
        "recent_analysis_tasks": [
            {"task_id": t.id, "document_id": t.document_id, "task_status": t.task_status,
             "current_step": t.current_step, "created_at": t.created_at} for t in recent_tasks
        ],
        "recent_documents": [
            {"id": d.id, "document_no": d.document_no, "document_type": d.document_type,
             "document_status": d.document_status, "total_amount": float(d.total_amount or 0)}
            for d in (await db.execute(scoped().order_by(FinancialDocument.updated_at.desc())
                                       .limit(6))).scalars().all()
        ],
    })


@router.get("/audit-logs", response_model=dict)
async def audit_logs(db: DbDep, user: CurrentUser, action_type: Optional[str] = None,
                     page: int = 1, page_size: int = 20):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ok({"items": [{"id": r.id, "user_id": r.user_id, "action_type": r.action_type,
                          "resource_type": r.resource_type, "resource_id": r.resource_id,
                          "detail": r.detail_json, "created_at": r.created_at} for r in rows],
               "total": total})
