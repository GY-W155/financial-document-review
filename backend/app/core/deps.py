"""FastAPI 依赖：认证、角色、数据归属权限。"""
from dataclasses import dataclass
from typing import Annotated, Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str = "未登录或登录已过期"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer Token 解析当前用户。"""
    if not creds or not creds.credentials:
        raise AuthError("未登录或登录已过期")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload.get("sub"))
    except ValueError as exc:
        raise AuthError("登录凭证已过期") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise AuthError("用户不存在")
    if user.status != "active":
        raise AuthError("账号已被禁用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_roles(
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)], codes: Iterable[str] | str
) -> User:
    """校验当前用户是否拥有任一角色（满足其一即可）。"""
    need = {codes} if isinstance(codes, str) else set(codes)
    user_has = {r.role_code for r in user.roles}
    if not user_has & need:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user


@dataclass
class DocScope:
    """单据数据归属解析结果。"""

    can_view_all: bool = False
    is_applicant_only: bool = False
    applicant_id: int | None = None


async def resolve_document_scope(user: User) -> DocScope:
    """解析用户对单据的数据权限。

    - admin / finance / approver => 可查看范围更大
    - applicant / 普通用户 => 仅本人单据
    """
    codes = {r.role_code for r in user.roles}
    if codes & {"admin", "finance", "approver"}:
        return DocScope(can_view_all=True, applicant_id=user.id)
    return DocScope(is_applicant_only=True, applicant_id=user.id)
