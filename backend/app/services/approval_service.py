"""审批流程引擎：工作流匹配、实例/任务创建、多节点流转。"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ApprovalInstance,
    ApprovalTask,
    ApprovalWorkflow,
    DocumentStatusLog,
    FinancialDocument,
    User,
)
from ..utils.helpers import to_float
from .audit import log_action


async def find_workflow(db, doc: FinancialDocument) -> Optional[ApprovalWorkflow]:
    """按单据类型 + 条件（金额区间/部门）匹配启用的工作流。

    若无匹配，回退到该单据类型的第一个启用工作流。
    """
    result = await db.execute(
        select(ApprovalWorkflow)
        .where(ApprovalWorkflow.document_type == doc.document_type)
        .where(ApprovalWorkflow.status == "active")
    )
    workflows = result.scalars().all()
    if not workflows:
        return None

    amount = to_float(doc.total_amount) or 0
    for wf in workflows:
        cond = wf.match_conditions_json or {}
        low = to_float(cond.get("amount_min")) if cond.get("amount_min") is not None else None
        high = to_float(cond.get("amount_max")) if cond.get("amount_max") is not None else None
        if low is not None and amount < low:
            continue
        if high is not None and amount > high:
            continue
        dept = cond.get("department")
        if dept and dept not in (doc.applicant_department, doc.budget_department):
            continue
        return wf
    return workflows[0] if workflows else None


async def list_approver_ids(db, role_code: str) -> list[int]:
    """返回拥有指定角色的用户 id。"""
    from ..models import Role, UserRole

    result = await db.execute(
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.role_code == role_code)
    )
    return [r[0] for r in result.all()]


async def start_approval(db, doc: FinancialDocument) -> ApprovalInstance:
    wf = await find_workflow(db, doc)
    if not wf:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="未配置匹配的审批流程，无法提交")

    instance = ApprovalInstance(
        workflow_id=wf.id,
        document_id=doc.id,
        document_version=doc.current_version,
        instance_status="running",
    )
    db.add(instance)
    await db.flush()

    first_node = next((n for n in wf.nodes if n.node_order == 1), None)
    if not wf.nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="审批流程无审批节点")
    first_node = wf.nodes[0]
    instance.current_node_id = first_node.id
    await _create_node_tasks(db, instance, first_node)
    return instance


async def _create_node_tasks(db, instance: ApprovalInstance, node) -> list[ApprovalTask]:
    approver_ids = await list_approver_ids(db, node.approver_role)
    tasks: list[ApprovalTask] = []
    for uid in approver_ids:
        task = ApprovalTask(
            instance_id=instance.id, node_id=node.id, approver_id=uid, task_status="pending"
        )
        db.add(task)
        tasks.append(task)
    if not tasks:  # 无匹配审批人时兜底：approver_id 空，等待有角色的人认领
        db.add(ApprovalTask(instance_id=instance.id, node_id=node.id, task_status="pending"))
    await db.flush()
    return tasks


async def get_task(db, task_id: int) -> ApprovalTask:
    task = (await db.execute(select(ApprovalTask).where(ApprovalTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批任务不存在")
    return task


async def _assert_can_process(db, user: User, task: ApprovalTask) -> None:
    from ..models import ApprovalWorkflowNode

    if task.approver_id is not None and task.approver_id != user.id:
        # 若指定了审批人但非本人，仍允许拥有该节点角色的人处理（any 模式）
        pass
    node = (await db.execute(select(ApprovalWorkflowNode).where(
        ApprovalWorkflowNode.id == task.node_id))).scalar_one()
    roles = {r.role_code for r in user.roles}
    if node.approver_role not in roles and "admin" not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您无权处理该审批任务")


async def approve_task(db, user: User, task_id: int, comment: str = "") -> dict:
    task = await get_task(db, task_id)
    await _assert_can_process(db, user, task)
    if task.task_status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务已处理")

    task.task_status = "approved"
    task.review_comment = comment
    task.processed_at = datetime.utcnow()
    instance = (await db.execute(select(ApprovalInstance).where(
        ApprovalInstance.id == task.instance_id))).scalar_one()
    wf = (await db.execute(select(ApprovalWorkflow).where(
        ApprovalWorkflow.id == instance.workflow_id))).scalar_one()

    nodes = sorted(wf.nodes, key=lambda x: x.node_order)
    cur_idx = next((i for i, n in enumerate(nodes) if n.id == instance.current_node_id), None)
    next_node = nodes[cur_idx + 1] if (cur_idx is not None and cur_idx + 1 < len(nodes)) else None

    if next_node is None:
        # 最后一个节点通过
        instance.instance_status = "approved"
        instance.current_node_id = nodes[cur_idx].id if cur_idx is not None else instance.current_node_id
        instance.finished_at = datetime.utcnow()
        doc = (await db.execute(select(FinancialDocument).where(
            FinancialDocument.id == instance.document_id))).scalar_one()
        doc.document_status = "approved"
        db.add(DocumentStatusLog(document_id=doc.id, from_status="pending_review",
                                 to_status="approved", operator_id=user.id, remark="审批通过"))
        await log_action(db, user.id, "approval.approve.finish", "document", doc.id, {})
        await db.commit()
        return {"task_id": task_id, "instance_status": "approved", "document_status": "approved"}
    else:
        instance.current_node_id = next_node.id
        await _create_node_tasks(db, instance, next_node)
        await log_action(db, user.id, "approval.node.approve", "approval_instance", instance.id, {})
        await db.commit()
        return {"task_id": task_id, "instance_status": "running", "next_node_id": next_node.id}


async def return_task(db, user: User, task_id: int, comment: str = "") -> dict:
    task = await get_task(db, task_id)
    await _assert_can_process(db, user, task)
    if task.task_status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务已处理")
    task.task_status = "returned"
    task.review_comment = comment
    task.processed_at = datetime.utcnow()
    instance = (await db.execute(select(ApprovalInstance).where(
        ApprovalInstance.id == task.instance_id))).scalar_one()
    instance.instance_status = "returned"
    instance.finished_at = datetime.utcnow()
    doc = (await db.execute(select(FinancialDocument).where(
        FinancialDocument.id == instance.document_id))).scalar_one()
    doc.document_status = "returned"
    db.add(DocumentStatusLog(document_id=doc.id, from_status="pending_review",
                             to_status="returned", operator_id=user.id, remark="退回修改"))
    await log_action(db, user.id, "approval.return", "document", doc.id, {})
    await db.commit()
    return {"task_id": task_id, "instance_status": "returned", "document_status": "returned"}


async def reject_task(db, user: User, task_id: int, comment: str = "") -> dict:
    task = await get_task(db, task_id)
    await _assert_can_process(db, user, task)
    if task.task_status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务已处理")
    task.task_status = "rejected"
    task.review_comment = comment
    task.processed_at = datetime.utcnow()
    instance = (await db.execute(select(ApprovalInstance).where(
        ApprovalInstance.id == task.instance_id))).scalar_one()
    instance.instance_status = "rejected"
    instance.finished_at = datetime.utcnow()
    doc = (await db.execute(select(FinancialDocument).where(
        FinancialDocument.id == instance.document_id))).scalar_one()
    doc.document_status = "rejected"
    db.add(DocumentStatusLog(document_id=doc.id, from_status="pending_review",
                             to_status="rejected", operator_id=user.id, remark="驳回"))
    await log_action(db, user.id, "approval.reject", "document", doc.id, {})
    await db.commit()
    return {"task_id": task_id, "instance_status": "rejected", "document_status": "rejected"}


async def list_my_tasks(db, user: User, task_status: str | None = "pending") -> list[dict]:
    """当前用户可见的审批任务（按节点角色匹配）。"""
    roles = {r.role_code for r in user.roles}
    from ..models import ApprovalWorkflowNode, Role

    result = await db.execute(select(ApprovalTask))
    tasks = result.scalars().all()
    out = []
    for t in tasks:
        node = (await db.execute(select(ApprovalWorkflowNode).where(
            ApprovalWorkflowNode.id == t.node_id))).scalar_one()
        if node.approver_role not in roles and "admin" not in roles:
            continue
        if task_status and t.task_status != task_status:
            continue
        instance = (await db.execute(select(ApprovalInstance).where(
            ApprovalInstance.id == t.instance_id))).scalar_one()
        doc = (await db.execute(select(FinancialDocument).where(
            FinancialDocument.id == instance.document_id))).scalar_one()
        out.append({
            "task_id": t.id, "instance_id": t.instance_id, "node_id": t.node_id,
            "node_name": node.node_name, "approver_role": node.approver_role,
            "task_status": t.task_status, "document_id": doc.id,
            "document_no": doc.document_no, "document_type": doc.document_type,
            "total_amount": float(doc.total_amount or 0), "created_at": t.created_at,
        })
    return out
