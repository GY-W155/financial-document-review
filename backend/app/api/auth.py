"""认证路由。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.common import ok, write_audit
from ..core.deps import CurrentUser, get_current_user
from ..core.security import create_access_token, verify_password
from ..database import get_db
from ..models import User
from ..schemas.auth import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(User).where(User.username == body.username).options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    token = create_access_token(user.id, {"roles": [r.role_code for r in user.roles]})
    await write_audit(db, user.id, "login", resource_type="auth")
    await db.commit()
    return ok({"access_token": token, "token_type": "bearer",
               "user": {"id": user.id, "username": user.username,
                        "display_name": user.display_name,
                        "roles": [{"role_code": r.role_code, "role_name": r.role_name} for r in user.roles]}})


@router.get("/me")
async def me(user: CurrentUser):
    return ok({"id": user.id, "username": user.username, "display_name": user.display_name,
               "roles": [r.role_code for r in user.roles]},
              message="ok")
