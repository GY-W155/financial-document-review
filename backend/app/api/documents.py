"""单据/明细/附件/分析触发 路由。"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser, require_roles
from ..database import get_db
from ..schemas.document import DocumentIn, LineItemIn
from ..services import document_service, parse_service, attachment_service, analysis_service

router = APIRouter(prefix="/documents", tags=["documents"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=dict)
async def create_document(body: DocumentIn, db: DbDep, user: CurrentUser):
    doc = await document_service.create_document(db, user, body)
    return ok(document_service.document_to_dict(doc), "创建成功")


@router.get("", response_model=dict)
async def list_documents(db: DbDep, user: CurrentUser,
                         document_type: Optional[str] = None,
                         applicant: Optional[str] = None,
                         department: Optional[str] = None,
                         status: Optional[str] = None,
                         apply_from: Optional[str] = None,
                         apply_to: Optional[str] = None,
                         keyword: Optional[str] = None,
                         page: int = 1, page_size: int = 20):
    from datetime import date
    data = await document_service.list_documents(
        db, user, document_type=document_type, applicant=applicant, department=department,
        doc_status=status, apply_from=date.fromisoformat(apply_from) if apply_from else None,
        apply_to=date.fromisoformat(apply_to) if apply_to else None, keyword=keyword,
        page=page, page_size=page_size)
    return ok(data)


@router.get("/{document_id}", response_model=dict)
async def get_document(document_id: int, db: DbDep, user: CurrentUser):
    doc = await document_service.get_document(db, user, document_id)
    return ok(document_service.document_to_dict(doc))


@router.patch("/{document_id}", response_model=dict)
async def update_document(document_id: int, body: DocumentIn, db: DbDep, user: CurrentUser):
    doc = await document_service.update_document(db, user, document_id, body)
    return ok(document_service.document_to_dict(doc), "已更新")


@router.post("/{document_id}/copy", response_model=dict)
async def copy_document(document_id: int, db: DbDep, user: CurrentUser):
    return ok(await document_service.copy_document(db, user, document_id), "已复制")


@router.post("/{document_id}/submit", response_model=dict)
async def submit_document(document_id: int, db: DbDep, user: CurrentUser):
    return ok(await document_service.submit_document(db, user, document_id), "已提交审批")


@router.post("/{document_id}/withdraw", response_model=dict)
async def withdraw_document(document_id: int, db: DbDep, user: CurrentUser):
    return ok(await document_service.withdraw_document(db, user, document_id), "已撤回")


@router.post("/{document_id}/void", response_model=dict)
async def void_document(document_id: int, db: DbDep, user: CurrentUser):
    return ok(await document_service.void_document(db, user, document_id), "已作废")


@router.get("/{document_id}/amount-comparison", response_model=dict)
async def amount_comparison(document_id: int, db: DbDep, user: CurrentUser):
    from ..services.analysis_service import build_amount_comparison, load_context
    from ..models import AnalysisTask

    doc = await document_service.get_document(db, user, document_id)
    # 取最近一次成功分析任务构建上下文
    from sqlalchemy import select
    task = (await db.execute(select(AnalysisTask).where(
        AnalysisTask.document_id == doc.id, AnalysisTask.task_status == "succeeded")
        .order_by(AnalysisTask.id.desc()))).scalars().first()
    if not task:
        return ok({"document_total": float(doc.total_amount or 0), "note": "尚未分析"},
                  "暂无金额核对")
    ctx = await load_context(db, task)
    return ok(build_amount_comparison(ctx))


# ---- 明细 ----
@router.post("/{document_id}/line-items", response_model=dict)
async def add_line_item(document_id: int, body: LineItemIn, db: DbDep, user: CurrentUser):
    return ok(await document_service.add_line_item(db, user, document_id, body))


@router.patch("/{document_id}/line-items/{line_item_id}", response_model=dict)
async def update_line_item(document_id: int, line_item_id: int, body: LineItemIn,
                           db: DbDep, user: CurrentUser):
    return ok(await document_service.update_line_item(db, user, document_id, line_item_id, body))


@router.delete("/{document_id}/line-items/{line_item_id}", response_model=dict)
async def delete_line_item(document_id: int, line_item_id: int, db: DbDep, user: CurrentUser):
    return ok(await document_service.delete_line_item(db, user, document_id, line_item_id))


# ---- 附件 ----
@router.post("/{document_id}/attachments", response_model=dict)
async def upload_attachment(document_id: int, db: DbDep, user: CurrentUser,
                            file: UploadFile = File(...)):
    return ok(await attachment_service.save_attachment(db, user, document_id, file), "上传成功")


@router.get("/{document_id}/attachments/{attachment_id}", response_model=dict)
async def download_attachment(document_id: int, attachment_id: int, db: DbDep, user: CurrentUser):
    att = await attachment_service.get_attachment(db, user, document_id, attachment_id)
    content = await attachment_service.read_attachment_content(att)
    from fastapi.responses import Response
    return Response(content=content, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{att.file_name}"'})


@router.delete("/{document_id}/attachments/{attachment_id}", response_model=dict)
async def delete_attachment(document_id: int, attachment_id: int, db: DbDep, user: CurrentUser):
    return ok(await attachment_service.delete_attachment(db, user, document_id, attachment_id))


@router.post("/{document_id}/attachments/{attachment_id}/parse", response_model=dict)
async def parse_attachment(document_id: int, attachment_id: int, db: DbDep, user: CurrentUser):
    att = await attachment_service.get_attachment(db, user, document_id, attachment_id)
    result = await parse_service.parse_attachment(db, att)
    return ok(result)


# ---- 分析触发 ----
@router.post("/{document_id}/analysis", response_model=dict)
async def run_analysis_endpoint(document_id: int, db: DbDep, user: CurrentUser,
                                session_id: Optional[int] = None):
    doc = await document_service.get_document(db, user, document_id)
    task = await analysis_service.create_analysis_task(db, doc, session_id)
    await db.commit()
    result = await analysis_service.run_analysis(db, task)
    return ok({"task_id": task.id, **result}, "分析完成")
