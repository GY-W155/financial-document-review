"""审核会话（多轮对话）路由。"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser
from ..database import get_db
from ..schemas.session import MessageIn, SessionCreate
from ..services import session_service

router = APIRouter(prefix="/review-sessions", tags=["sessions"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=dict)
async def create_session(body: SessionCreate, db: DbDep, user: CurrentUser):
    s = await session_service.create_session(db, user, body.document_type, body.document_no)
    return ok({"id": s.id, "document_type": s.document_type, "document_no": s.document_no,
               "session_status": s.session_status},
              "会话已创建")


@router.post("/{session_id}/messages", response_model=dict)
async def send_message(session_id: int, body: MessageIn, db: DbDep, user: CurrentUser):
    resp = await session_service.handle_message(db, user, session_id, body.content)
    return ok(resp)


@router.get("/{session_id}/messages", response_model=dict)
async def list_messages(session_id: int, db: DbDep, user: CurrentUser):
    return ok(await session_service.list_messages(db, user, session_id))
