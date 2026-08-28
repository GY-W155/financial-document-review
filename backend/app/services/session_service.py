"""审核会话服务：多轮交互，槽位澄清（单据类型/编号），发起分析。"""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import DOCUMENT_TYPES
from ..models import FinancialDocument, ReviewSession, SessionMessage, User
from .analysis_service import create_analysis_task as _create_task, run_analysis
from .audit import log_action

TYPE_HINTS = {
    "付款": "对公付款单", "预付款": "预付款单", "批量": "批量付款单",
    "报销": "费用报销单", "差旅": "差旅报销单",
}
DOC_NO_RE = re.compile(r"DN-[A-Z]+-\d{8}-\d+")


def _detect_type(text: str) -> str | None:
    for key, val in TYPE_HINTS.items():
        if key in text:
            return val
    for t in DOCUMENT_TYPES:
        if t in text:
            return t
    return None


def _detect_doc_no(text: str) -> str | None:
    m = DOC_NO_RE.search(text)
    return m.group(0) if m else None


async def create_session(db: AsyncSession, user: User, document_type=None, document_no=None) -> ReviewSession:
    session = ReviewSession(user_id=user.id, document_type=document_type,
                            document_no=document_no, session_status="ongoing",
                            confirmed_slots={})
    db.add(session)
    await db.flush()
    db.add(SessionMessage(session_id=session.id, role="assistant",
                          content="您好，我是财务单据智能审核助手。请告诉我您要分析的单据类型与单据编号。",
                          message_type="info"))
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_or_404(db: AsyncSession, user: User, session_id: int) -> ReviewSession:
    session = (await db.execute(select(ReviewSession).where(
        ReviewSession.id == session_id))).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if session.user_id != user.id and "admin" not in {r.role_code for r in user.roles}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该会话")
    return session


async def handle_message(db: AsyncSession, user: User, session_id: int, content: str) -> dict:
    session = await get_session_or_404(db, user, session_id)
    db.add(SessionMessage(session_id=session.id, role="user", content=content, message_type="text"))
    await db.flush()

    slots = dict(session.confirmed_slots or {})
    type_from_msg = _detect_type(content)
    no_from_msg = _detect_doc_no(content)

    # 更新已确认槽位
    if type_from_msg and not slots.get("document_type"):
        slots["document_type"] = type_from_msg
    if no_from_msg and not slots.get("document_no"):
        slots["document_no"] = no_from_msg

    # 缺少类型或编号 -> 澄清
    if not slots.get("document_type"):
        reply = "请指定要分析的单据类型。可选：{}".format("、".join(DOCUMENT_TYPES))
        return await _reply(db, session, slots, "clarification", reply,
                            {"slot_name": "document_type", "candidate_values": list(DOCUMENT_TYPES)})
    if not slots.get("document_no"):
        reply = "请提供单据编号（形如 DN-XXX-YYYYMMDD-1234）。"
        return await _reply(db, session, slots, "clarification", reply, {"slot_name": "document_no"})

    # 信息完整 -> 查询单据
    doc = await _find_document(db, user, slots["document_type"], slots["document_no"])
    if not doc:
        reply = "未查询到符合条件（{} / {}）的单据，请核对类型或编号。".format(
            slots["document_type"], slots["document_no"])
        return await _reply(db, session, slots, "error", reply,
                            {"error_code": "DOC_NOT_FOUND", "error_message": reply})

    # 发起分析
    task = await _create_task(db, doc, session.id)
    session.session_status = "running"
    await db.commit()
    result = await run_analysis(db, task)

    reply = f"已完成「{doc.document_no}」的风险分析：整体风险等级 **{result['overall_level']}**，共 {result['findings']} 项风险项。"
    return await _reply(db, session, slots, "done", reply, {
        "task_id": task.id, "report_id": result["report_id"],
        "overall_risk_level": result["overall_level"],
    })


async def _find_document(db: AsyncSession, user: User, doc_type: str, doc_no: str) -> FinancialDocument | None:
    result = await db.execute(select(FinancialDocument).where(
        FinancialDocument.document_type == doc_type,
        FinancialDocument.document_no == doc_no,
    ))
    doc = result.scalar_one_or_none()
    if not doc:
        return None
    from .permissions import assert_can_view_document

    try:
        assert_can_view_document(user, doc)
    except Exception:
        return None
    return doc


async def _reply(db: AsyncSession, session: ReviewSession, slots: dict,
                 message_type: str, text: str, data: Any = None) -> dict:
    session.confirmed_slots = slots
    db.add(SessionMessage(session_id=session.id, role="assistant", content=text,
                          message_type=message_type))
    await log_action(db, session.user_id, "session.message", "session", session.id,
                     {"type": message_type})
    await db.commit()
    return {"message_type": message_type, "reply_text": text, "data": data}


async def list_messages(db: AsyncSession, user: User, session_id: int) -> list[dict]:
    session = await get_session_or_404(db, user, session_id)
    result = await db.execute(select(SessionMessage)
                              .where(SessionMessage.session_id == session.id)
                              .order_by(SessionMessage.id))
    return [{"id": m.id, "role": m.role, "content": m.content, "message_type": m.message_type,
             "created_at": m.created_at} for m in result.scalars().all()]
