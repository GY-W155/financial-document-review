"""附件服务：上传/校验/哈希/删除/下载/访问控制。"""
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import DocumentAttachment, FinancialDocument, User
from .audit import log_action
from .document_service import get_document


def _safe_name(filename: str) -> str:
    name = re.sub(r"[^\w.一-龥-]", "_", Path(filename).name)
    return name or "file"


async def save_attachment(db, user: User, document_id: int, file: UploadFile) -> dict:
    doc = await get_document(db, user, document_id, for_write=True)
    ext = (file.filename or "").lower().split(".")[-1]
    if ext not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"不支持的文件类型 {ext}，允许 pdf/png/jpg")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件超过大小限制")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空文件")

    file_hash = hashlib.sha256(content).hexdigest()
    # 存储到 uploads/{doc_type}/{document_no}/{hash}{ext}
    rel_dir = Path(settings.STORAGE_DIR) / f"doc_{doc.id}" / doc.document_no
    rel_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_name(file.filename or f"att-{file_hash}.{ext}")
    rel_path = rel_dir / safe_name
    rel_path.write_bytes(content)

    att = DocumentAttachment(
        document_id=doc.id,
        document_version=doc.current_version,
        file_name=safe_name,
        file_type=ext,
        file_size=len(content),
        file_path=str(rel_path),
        file_hash=file_hash,
        storage_status="stored",
        parse_status="pending",
    )
    db.add(att)
    await log_action(db, user.id, "attachment.upload", "attachment", "", {"document_id": doc.id})
    await db.commit()
    await db.refresh(att)
    return {
        "id": att.id, "file_name": att.file_name, "file_type": att.file_type,
        "file_size": att.file_size, "storage_status": att.storage_status,
        "parse_status": att.parse_status,
    }


async def get_attachment(db, user: User, document_id: int, attachment_id: int) -> DocumentAttachment:
    doc = await get_document(db, user, document_id)
    att = next((a for a in doc.attachments if a.id == attachment_id), None)
    if not att:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在")
    return att


async def read_attachment_content(att: DocumentAttachment) -> bytes:
    path = Path(att.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件文件丢失")
    return path.read_bytes()


async def delete_attachment(db, user: User, document_id: int, attachment_id: int) -> dict:
    att = await get_attachment(db, user, document_id, attachment_id)
    path = Path(att.file_path)
    if path.exists():
        os.remove(path)
    await db.delete(att)
    await log_action(db, user.id, "attachment.delete", "attachment", attachment_id, {})
    await db.commit()
    return {"deleted": attachment_id}
