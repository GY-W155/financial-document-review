"""审批任务与审批流程配置路由。

路径兼容两套写法（均指向同一实现）：
  - 现行前端路径：/approval/tasks、/approval/workflows
  - 需求 2.7.11 规格路径：/approval-tasks、/approval-workflows
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser, require_roles
from ..database import get_db
from ..models import ApprovalWorkflow, ApprovalWorkflowNode
from ..schemas.approval import WorkflowIn
from ..services import approval_service
from ..services.audit import log_action

router = APIRouter(tags=["approval"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


def workflow_to_dict(w: ApprovalWorkflow) -> dict:
    """手动序列化：把 match_conditions_json 映射为 match_conditions，规避字段名差异。"""
    return {
        "id": w.id,
        "workflow_name": w.workflow_name,
        "document_type": w.document_type,
        "match_conditions": w.match_conditions_json or {},
        "status": w.status,
        "nodes": [{"id": n.id, "node_name": n.node_name, "node_order": n.node_order,
                   "approver_role": n.approver_role, "approval_mode": n.approval_mode}
                  for n in w.nodes],
    }


# ---- 任务列表 + 处理：双路径 ----
@router.get("/approval/tasks")
@router.get("/approval-tasks")
async def list_tasks(db: DbDep, user: CurrentUser, status: Optional[str] = None):
    return ok(await approval_service.list_my_tasks(db, user, status))


@router.post("/approval/tasks/{task_id}/approve")
@router.post("/approval-tasks/{task_id}/approve")
async def approve(task_id: int, db: DbDep, user: CurrentUser, comment: str = ""):
    return ok(await approval_service.approve_task(db, user, task_id, comment), "审批通过")


@router.post("/approval/tasks/{task_id}/return")
@router.post("/approval-tasks/{task_id}/return")
async def approve_return(task_id: int, db: DbDep, user: CurrentUser, comment: str = ""):
    return ok(await approval_service.return_task(db, user, task_id, comment), "退回修改")


@router.post("/approval/tasks/{task_id}/reject")
@router.post("/approval-tasks/{task_id}/reject")
async def approve_reject(task_id: int, db: DbDep, user: CurrentUser, comment: str = ""):
    return ok(await approval_service.reject_task(db, user, task_id, comment), "已驳回")


# ---- 审批流程配置：双路径 ----
@router.get("/approval/workflows")
@router.get("/approval-workflows")
async def list_workflows(db: DbDep, user: CurrentUser):
    wfs = (await db.execute(select(ApprovalWorkflow))).scalars().all()
    return ok([workflow_to_dict(w) for w in wfs])


@router.post("/approval/workflows")
@router.post("/approval-workflows")
async def create_workflow(body: WorkflowIn, db: DbDep, user: CurrentUser):
    await require_roles(user, db, ["admin"])
    wf = ApprovalWorkflow(workflow_name=body.workflow_name, document_type=body.document_type,
                          match_conditions_json=body.match_conditions, status="active")
    db.add(wf)
    await db.flush()
    for n in body.nodes:
        db.add(ApprovalWorkflowNode(workflow_id=wf.id, node_name=n.node_name,
                                    node_order=n.node_order, approver_role=n.approver_role,
                                    approval_mode=n.approval_mode))
    await log_action(db, user.id, "workflow.create", "workflow", wf.id,
                     {"document_type": body.document_type})
    await db.commit()
    await db.refresh(wf)
    return ok(workflow_to_dict(wf), "已创建")


@router.patch("/approval/workflows/{workflow_id}")
@router.patch("/approval-workflows/{workflow_id}")
async def update_workflow(workflow_id: int, body: WorkflowIn, db: DbDep, user: CurrentUser):
    wf = (await db.execute(select(ApprovalWorkflow).where(
        ApprovalWorkflow.id == workflow_id))).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    wf.workflow_name = body.workflow_name
    wf.document_type = body.document_type
    wf.match_conditions_json = body.match_conditions
    for old in list(wf.nodes):
        await db.delete(old)
    await db.flush()
    for n in body.nodes:
        db.add(ApprovalWorkflowNode(workflow_id=wf.id, node_name=n.node_name,
                                    node_order=n.node_order, approver_role=n.approver_role,
                                    approval_mode=n.approval_mode))
    await log_action(db, user.id, "workflow.update", "workflow", wf.id, {})
    await db.commit()
    await db.refresh(wf)
    return ok(workflow_to_dict(wf), "已更新")
