"""统一响应包裹与审计、常量。"""
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog
from ..utils.helpers import paginate

# 单据类型 / 角色 常量
DOCUMENT_TYPES = {
    "对公付款单", "预付款单", "批量付款单", "费用报销单", "差旅报销单",
}
ROLE_CODES = {"applicant", "approver", "finance", "admin"}

RECOMMENDATIONS = {"建议通过", "补充材料", "人工复核", "建议驳回"}


def ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


def fail(code: int = 1, message: str = "error", status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def page_resp(items: list, total: int, page: int, page_size: int) -> dict:
    return ok(paginate(items, total, page, page_size))


async def write_audit(
    db: AsyncSession,
    user_id: int | None,
    action_type: str,
    resource_type: str = "",
    resource_id: str | int = "",
    detail: dict | None = None,
) -> None:
    """写审计日志（不自动 commit，交由调用方事务）。"""
    db.add(
        AuditLog(
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            detail_json=detail or {},
        )
    )
