"""审计日志封装。"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import write_audit


async def log_action(
    db: AsyncSession,
    user_id: int | None,
    action_type: str,
    resource_type: str = "",
    resource_id: str | int = "",
    detail: dict | None = None,
) -> None:
    await write_audit(db, user_id, action_type, resource_type, resource_id, detail)
