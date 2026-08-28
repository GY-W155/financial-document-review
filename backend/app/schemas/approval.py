"""审批工作流/实例/任务 schema。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowNodeIn(BaseModel):
    node_name: str
    node_order: int = 1
    approver_role: str
    approval_mode: str = "any"


class WorkflowNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    node_name: str
    node_order: int
    approver_role: str
    approval_mode: str


class WorkflowIn(BaseModel):
    workflow_name: str
    document_type: str
    match_conditions: dict[str, Any] = Field(default_factory=dict)
    nodes: list[WorkflowNodeIn] = Field(default_factory=list)


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workflow_name: str
    document_type: str
    match_conditions: dict
    status: str
    nodes: list[WorkflowNodeOut] = []


class ApprovalTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instance_id: int
    node_id: int
    approver_id: Optional[int] = None
    task_status: str
    review_comment: str
    created_at: datetime
    processed_at: Optional[datetime] = None


class ApproveIn(BaseModel):
    comment: str = ""
    approved: bool = None  # 通过/退回/驳回 由接口区分


class ManualReviewIn(BaseModel):
    review_result: str = "approved"  # approved / returned / rejected
    review_comment: str = ""
