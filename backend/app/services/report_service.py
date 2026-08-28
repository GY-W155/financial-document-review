"""报告：读取、人工复核、风险项复核状态、导出。"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ManualReview, ReviewReport, RiskFinding, User
from .audit import log_action
from .permissions import assert_can_view_document


async def get_report(db: AsyncSession, report_id: int) -> ReviewReport:
    report = (await db.execute(select(ReviewReport).where(
        ReviewReport.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


async def get_report_by_task(db: AsyncSession, task_id: int) -> ReviewReport:
    report = (await db.execute(select(ReviewReport).where(
        ReviewReport.task_id == task_id).order_by(ReviewReport.id.desc()))).scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    return report


def report_to_dict(report: ReviewReport) -> dict:
    return {
        "id": report.id, "task_id": report.task_id, "document_id": report.document_id,
        "overall_risk_level": report.overall_risk_level,
        "risk_summary": report.risk_summary_json, "amount_comparison": report.amount_comparison_json,
        "recommendation": report.recommendation, "report_markdown": report.report_markdown,
        "created_at": report.created_at,
        "manual_reviews": [{
            "id": m.id, "reviewer_id": m.reviewer_id, "review_result": m.review_result,
            "review_comment": m.review_comment, "reviewed_at": m.reviewed_at,
        } for m in report.manual_reviews],
    }


async def update_finding_status(db: AsyncSession, user: User, finding_id: int, review_status: str) -> dict:
    if review_status not in {"pending", "confirmed", "dismissed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法复核状态")
    finding = (await db.execute(select(RiskFinding).where(
        RiskFinding.id == finding_id))).scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险项不存在")
    finding.review_status = review_status
    await log_action(db, user.id, "risk_finding.review_status", "risk_finding", finding_id,
                     {"review_status": review_status})
    await db.commit()
    return {"finding_id": finding_id, "review_status": review_status}


async def add_manual_review(db: AsyncSession, user: User, report_id: int,
                            review_result: str, review_comment: str) -> dict:
    report = await get_report(db, report_id)
    if review_result not in {"approved", "returned", "rejected", "manual"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法复核结论")
    review = ManualReview(report_id=report.id, reviewer_id=user.id,
                          review_result=review_result, review_comment=review_comment)
    db.add(review)
    await log_action(db, user.id, "manual_review.submit", "report", report.id,
                     {"result": review_result})
    await db.commit()
    return {"id": review.id, "review_result": review_result, "review_comment": review_comment,
            "reviewed_at": review.reviewed_at}
