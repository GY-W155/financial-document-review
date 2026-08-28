"""供应商风险路由。"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser, require_roles
from ..database import get_db
from ..schemas.supplier import MarketPriceIn, RuleIn, RulePatch, RuleOut
from ..models import AuditRule, MarketPriceReference, User
from ..services.audit import log_action
from ..services.supplier_service import get_supplier_risk

router = APIRouter(prefix="/suppliers", tags=["suppliers"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{supplier_code}/risks", response_model=dict)
async def supplier_risks(supplier_code: str, db: DbDep, user: CurrentUser):
    data = await get_supplier_risk(db, supplier_code)
    if not data:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return ok(data)
