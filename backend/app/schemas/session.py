"""审核会话（多轮对话）schema。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    document_type: Optional[str] = None
    document_no: Optional[str] = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_type: Optional[str] = None
    document_no: Optional[str] = None
    session_status: str
    confirmed_slots: dict


class MessageIn(BaseModel):
    content: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    message_type: str
    created_at: datetime


class MessageResponse(BaseModel):
    message_type: str  # clarification / info / analysis_started / error
    reply_text: str
    data: Any = None
