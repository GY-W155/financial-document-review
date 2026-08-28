"""审核规则配置 与 市场价参考 路由。"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.common import ok
from ..core.deps import CurrentUser, require_roles
from ..database import get_db
from ..models import AuditRule, MarketPriceReference
from ..schemas.supplier import MarketPriceIn, RuleIn, RulePatch
from ..services.audit import log_action

router = APIRouter(prefix="/rules", tags=["rules"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=dict)
async def list_rules(db: DbDep, user: CurrentUser):
    rules = (await db.execute(select(AuditRule))).scalars().all()
    return ok([{"id": r.id, "rule_code": r.rule_code, "rule_name": r.rule_name,
                "rule_category": r.rule_category, "threshold": r.threshold,
                "status": r.status} for r in rules])


@router.post("", response_model=dict)
async def create_rule(body: RuleIn, db: DbDep, user: CurrentUser):
    await require_roles(user, db, ["finance", "admin"])
    rule = AuditRule(rule_code=body.rule_code, rule_name=body.rule_name, threshold=body.threshold)
    db.add(rule)
    await log_action(db, user.id, "rule.create", "rule", body.rule_code, {"threshold": body.threshold})
    await db.commit()
    await db.refresh(rule)
    return ok({"id": rule.id, "rule_code": rule.rule_code, "rule_name": rule.rule_name,
               "threshold": rule.threshold, "status": rule.status})


@router.patch("/{rule_id}", response_model=dict)
async def update_rule(rule_id: int, body: RulePatch, db: DbDep, user: CurrentUser):
    rule = (await db.execute(select(AuditRule).where(AuditRule.id == rule_id))).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    if body.threshold is not None:
        rule.threshold = body.threshold
    if body.rule_name is not None:
        rule.rule_name = body.rule_name
    if body.status is not None:
        rule.status = body.status
    await log_action(db, user.id, "rule.update", "rule", rule.rule_code,
                     {"threshold": body.threshold})
    await db.commit()
    return ok({"id": rule.id, "rule_code": rule.rule_code, "rule_name": rule.rule_name,
               "threshold": rule.threshold, "status": rule.status})


# ---- 市场价参考 ----
@router.get("/market-prices", response_model=dict)
async def list_market_prices(db: DbDep, user: CurrentUser):
    refs = (await db.execute(select(MarketPriceReference))).scalars().all()
    return ok([{"id": r.id, "item_name": r.item_name, "specification": r.specification,
                "region": r.region, "price_min": float(r.price_min or 0),
                "price_max": float(r.price_max or 0), "currency": r.currency,
                "source_name": r.source_name, "effective_date": r.effective_date}
               for r in refs])


@router.post("/market-prices", response_model=dict)
async def create_market_price(body: MarketPriceIn, db: DbDep, user: CurrentUser):
    await require_roles(user, db, ["finance", "admin"])
    ref = MarketPriceReference(**body.model_dump())
    db.add(ref)
    await log_action(db, user.id, "market_price.create", "market_price", body.item_name, {})
    await db.commit()
    return ok({"id": ref.id, "item_name": ref.item_name})
