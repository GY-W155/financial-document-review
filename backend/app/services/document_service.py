"""单据业务逻辑：创建/编辑/复制/提交/撤回/作废/查询，明细维护。"""
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from ..models import (
    DocumentLineItem,
    DocumentStatusLog,
    DocumentVersion,
    FinancialDocument,
    User,
)
from ..schemas.document import DocumentIn, LineItemIn
from .audit import log_action
from .doc_no import generate_document_no
from .permissions import assert_can_write_document, assert_can_view_document


def document_to_dict(doc: FinancialDocument) -> dict:
    return {
        "id": doc.id,
        "document_type": doc.document_type,
        "document_no": doc.document_no,
        "applicant_id": doc.applicant_id,
        "applicant_department": doc.applicant_department,
        "budget_department": doc.budget_department,
        "payee_name": doc.payee_name,
        "payee_account": doc.payee_account,
        "expense_category": doc.expense_category,
        "total_amount": float(doc.total_amount or 0),
        "currency": doc.currency,
        "apply_date": doc.apply_date.isoformat() if doc.apply_date else None,
        "reason_text": doc.reason_text,
        "document_status": doc.document_status,
        "current_version": doc.current_version,
        "extra_fields": doc.extra_fields_json or {},
        "line_items": [
            {
                "id": li.id,
                "item_type": li.item_type,
                "item_name": li.item_name,
                "expense_date": li.expense_date.isoformat() if li.expense_date else None,
                "expense_location": li.expense_location,
                "quantity": float(li.quantity or 1),
                "unit_price": float(li.unit_price or 0),
                "amount": float(li.amount or 0),
                "remark": li.remark,
            }
            for li in doc.line_items
        ],
        "attachments": [
            {
                "id": a.id,
                "file_name": a.file_name,
                "file_type": a.file_type,
                "file_size": a.file_size,
                "storage_status": a.storage_status,
                "parse_status": a.parse_status,
                "created_at": a.created_at,
            }
            for a in doc.attachments
        ],
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


async def load_doc_eager(db, document_id: int) -> FinancialDocument:
    """重新加载单据并一次性加载 relationships（避免异步惰性加载报错）。"""
    from ..models import DocumentAttachment

    result = await db.execute(
        select(FinancialDocument)
        .where(FinancialDocument.id == document_id)
        .options(
            selectinload(FinancialDocument.line_items),
            selectinload(FinancialDocument.attachments)
            .selectinload(DocumentAttachment.parse_result),
        )
    )
    return result.scalar_one()


async def get_document(db, user: User, document_id: int, for_write: bool = False) -> FinancialDocument:
    result = await db.execute(
        select(FinancialDocument).where(FinancialDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="单据不存在")
    if for_write:
        assert_can_write_document(user, doc)
    else:
        assert_can_view_document(user, doc)
    return doc


async def list_documents(db, user: User, *, document_type: str | None = None,
                         applicant: str | None = None, department: str | None = None,
                         doc_status: str | None = None, apply_from: date | None = None,
                         apply_to: date | None = None, keyword: str | None = None,
                         page: int = 1, page_size: int = 20) -> dict:
    from ..core.deps import resolve_document_scope

    scope = await resolve_document_scope(user)
    stmt = select(FinancialDocument)
    if not scope.can_view_all:
        stmt = stmt.where(FinancialDocument.applicant_id == user.id)
    if document_type:
        stmt = stmt.where(FinancialDocument.document_type == document_type)
    if doc_status:
        stmt = stmt.where(FinancialDocument.document_status == doc_status)
    if department:
        stmt = stmt.where(
            (FinancialDocument.applicant_department == department)
            | (FinancialDocument.budget_department == department)
        )
    if apply_from:
        stmt = stmt.where(FinancialDocument.apply_date >= apply_from)
    if apply_to:
        stmt = stmt.where(FinancialDocument.apply_date <= apply_to)
    if keyword:
        stmt = stmt.where(
            FinancialDocument.document_no.contains(keyword)
            | FinancialDocument.payee_name.contains(keyword)
            | FinancialDocument.reason_text.contains(keyword)
        )

    total_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = total_result.scalar_one()
    stmt = stmt.order_by(FinancialDocument.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = [document_to_dict(d) for d in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def create_document(db, user: User, data: DocumentIn) -> FinancialDocument:
    doc = FinancialDocument(
        document_type=data.document_type,
        document_no=generate_document_no(data.document_type),
        applicant_id=user.id,
        applicant_department=data.applicant_department or "",
        budget_department=data.budget_department,
        payee_name=data.payee_name,
        payee_account=data.payee_account,
        expense_category=data.expense_category,
        total_amount=data.total_amount,
        currency=data.currency,
        apply_date=data.apply_date,
        reason_text=data.reason_text,
        document_status="draft",
        current_version=1,
        extra_fields_json=data.extra_fields,
    )
    db.add(doc)
    await db.flush()
    for li in data.line_items:
        db.add(DocumentLineItem(document_id=doc.id, **line_item_kwargs(li)))
    # 新建时 doc 尚未从库加载，直接用请求数据构造快照，避免异步惰性加载
    snapshot = {
        "document_type": doc.document_type, "document_no": doc.document_no,
        "applicant_id": doc.applicant_id, "applicant_department": doc.applicant_department,
        "budget_department": doc.budget_department, "total_amount": float(doc.total_amount or 0),
        "currency": doc.currency, "extra_fields": doc.extra_fields_json or {},
        "line_items": [{"item_type": li.item_type, "item_name": li.item_name,
                        "amount": float(li.amount or 0),
                        "expense_date": li.expense_date.isoformat() if li.expense_date else None,
                        "expense_location": li.expense_location} for li in data.line_items],
    }
    db.add(DocumentVersion(document_id=doc.id, version_no=1,
                          document_snapshot_json=snapshot, created_by=user.id))
    await log_action(db, user.id, "document.create", "document", doc.id,
                     {"document_no": doc.document_no, "type": doc.document_type})
    await db.commit()
    return await load_doc_eager(db, doc.id)


async def update_document(db, user: User, document_id: int, data: DocumentIn) -> FinancialDocument:
    doc = await get_document(db, user, document_id, for_write=True)
    if doc.document_status not in {"draft", "returned"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="仅草稿或退回状态的单据可编辑")
    doc.applicant_department = data.applicant_department or doc.applicant_department
    doc.budget_department = data.budget_department
    doc.payee_name = data.payee_name
    doc.payee_account = data.payee_account
    doc.expense_category = data.expense_category
    doc.total_amount = data.total_amount
    doc.currency = data.currency or doc.currency
    doc.apply_date = data.apply_date
    doc.reason_text = data.reason_text
    doc.extra_fields_json = data.extra_fields
    doc.current_version += 1
    db.add(DocumentVersion(document_id=doc.id, version_no=doc.current_version,
                           document_snapshot_json=build_snapshot(doc), created_by=user.id))
    doc.version_snapshot = build_snapshot(doc)
    await log_action(db, user.id, "document.update", "document", doc.id, {})
    await db.commit()
    return await load_doc_eager(db, doc.id)


async def copy_document(db, user: User, document_id: int) -> dict:
    src = await get_document(db, user, document_id, for_write=True)
    new_doc = FinancialDocument(
        document_type=src.document_type,
        document_no=generate_document_no(src.document_type),
        applicant_id=user.id,
        applicant_department=src.applicant_department,
        budget_department=src.budget_department,
        payee_name=src.payee_name,
        payee_account=src.payee_account,
        expense_category=src.expense_category,
        total_amount=src.total_amount,
        currency=src.currency,
        apply_date=src.apply_date,
        reason_text=src.reason_text,
        document_status="draft",
        current_version=1,
        extra_fields_json=dict(src.extra_fields_json or {}),
    )
    db.add(new_doc)
    await db.flush()
    for li in src.line_items:
        db.add(DocumentLineItem(document_id=new_doc.id, **line_item_kwargs(LineItemIn(
            item_type=li.item_type, item_name=li.item_name, expense_date=li.expense_date,
            expense_location=li.expense_location, quantity=float(li.quantity or 1),
            unit_price=float(li.unit_price or 0), amount=float(li.amount or 0), remark=li.remark))))
    await log_action(db, user.id, "document.copy", "document", new_doc.id, {"from": src.document_no})
    await db.commit()
    return document_to_dict(await load_doc_eager(db, new_doc.id))


async def submit_document(db, user: User, document_id: int) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    if doc.document_status not in {"draft", "returned"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="仅草稿或退回状态的单据可提交")
    from .approval_service import start_approval
    from .analysis_service import create_analysis_task

    doc.document_status = "pending_review"
    doc.version_snapshot = build_snapshot(doc)
    await db.flush()
    instance = await start_approval(db, doc)  # 创建审批实例 + 首个任务
    analysis_task = await create_analysis_task(db, doc, session_id=None)
    db.add(DocumentStatusLog(document_id=doc.id, from_status="draft",
                             to_status="pending_review", operator_id=user.id, remark="提交审批"))
    await log_action(db, user.id, "document.submit", "document", doc.id, {})
    await db.commit()
    return {"document_id": doc.id, "document_status": doc.document_status,
            "instance_id": instance.id, "task_id": analysis_task.id}


async def withdraw_document(db, user: User, document_id: int) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    if doc.document_status not in {"pending_review", "reviewing"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前状态不可撤回")
    doc.document_status = "withdrawn"
    db.add(DocumentStatusLog(document_id=doc.id, from_status=doc.document_status,
                             to_status="withdrawn", operator_id=user.id, remark="撤回"))
    await log_action(db, user.id, "document.withdraw", "document", doc.id, {})
    await db.commit()
    return {"document_id": doc.id, "document_status": doc.document_status}


async def void_document(db, user: User, document_id: int) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    if doc.document_status in {"approved", "rejected"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已最终审结的单据不可作废")
    doc.document_status = "voided"
    db.add(DocumentStatusLog(document_id=doc.id, from_status=doc.document_status,
                             to_status="voided", operator_id=user.id, remark="作废"))
    await log_action(db, user.id, "document.void", "document", doc.id, {})
    await db.commit()
    return {"document_id": doc.id, "document_status": doc.document_status}


# ----- 明细 -----

def line_item_kwargs(data: LineItemIn) -> dict:
    return {
        "item_type": data.item_type,
        "item_name": data.item_name,
        "expense_date": data.expense_date,
        "expense_location": data.expense_location,
        "quantity": data.quantity,
        "unit_price": data.unit_price,
        "amount": data.amount,
        "remark": data.remark,
    }


async def add_line_item(db, user, document_id: int, data: LineItemIn) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    li = DocumentLineItem(document_id=doc.id, **line_item_kwargs(data))
    db.add(li)
    await log_action(db, user.id, "document.line_item.add", "document", doc.id, {})
    await db.commit()
    await db.refresh(li)
    return {"id": li.id, "document_id": doc.id, **line_item_kwargs(data)}


async def update_line_item(db, user, document_id: int, line_item_id: int, data: LineItemIn) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    li = next((x for x in doc.line_items if x.id == line_item_id), None)
    if not li:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明细不存在")
    li.item_type = data.item_type
    li.item_name = data.item_name
    li.expense_date = data.expense_date
    li.expense_location = data.expense_location
    li.quantity = data.quantity
    li.unit_price = data.unit_price
    li.amount = data.amount
    li.remark = data.remark
    await log_action(db, user.id, "document.line_item.update", "document", doc.id, {})
    await db.commit()
    return {"id": li.id, "document_id": doc.id, **line_item_kwargs(data)}


async def delete_line_item(db, user, document_id: int, line_item_id: int) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    li = next((x for x in doc.line_items if x.id == line_item_id), None)
    if not li:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="明细不存在")
    await db.delete(li)
    await log_action(db, user.id, "document.line_item.delete", "document", doc.id, {})
    await db.commit()
    return {"deleted": line_item_id}


def build_snapshot(doc: FinancialDocument) -> dict:
    return {
        "document_type": doc.document_type,
        "document_no": doc.document_no,
        "applicant_id": doc.applicant_id,
        "applicant_department": doc.applicant_department,
        "budget_department": doc.budget_department,
        "total_amount": float(doc.total_amount or 0),
        "currency": doc.currency,
        "extra_fields": doc.extra_fields_json or {},
        "line_items": [document_line_item_to_dict(li) for li in doc.line_items],
    }


def document_line_item_to_dict(li: DocumentLineItem) -> dict:
    return {
        "item_type": li.item_type,
        "item_name": li.item_name,
        "amount": float(li.amount or 0),
        "expense_date": li.expense_date.isoformat() if li.expense_date else None,
        "expense_location": li.expense_location,
    }
