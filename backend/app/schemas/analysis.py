"""风险分析/报告/金额核对 schema。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class RiskFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    risk_type: str
    risk_level: str
    risk_title: str
    description: str
    actual_value: dict
    reference_value: dict
    threshold: dict
    evidence: dict
    suggestion_text: str
    review_status: str
    created_at: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    document_id: int
    overall_risk_level: str
    risk_summary: dict
    amount_comparison: dict
    recommendation: str
    report_markdown: str
    created_at: datetime


class FindingReviewIn(BaseModel):
    review_status: str  # confirmed / dismissed / pending


class ManualReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reviewer_id: int
    review_result: str
    review_comment: str
    reviewed_at: datetime
