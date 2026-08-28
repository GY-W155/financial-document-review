"""供应商/市场价/规则 schema。"""
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SupplierRiskOut(BaseModel):
    supplier_code: str
    supplier_name: str
    credit_status: str
    blacklist_status: str
    risk_tags: list
    bank_accounts: list
    detail: dict = Field(default_factory=dict)


class MarketPriceIn(BaseModel):
    item_name: str
    specification: str = ""
    region: str = ""
    price_min: float = 0
    price_max: float = 0
    currency: str = "CNY"
    source_name: str = ""
    effective_date: date | None = None


class RuleBase(BaseModel):
    rule_code: str
    rule_name: str
    threshold: dict = Field(default_factory=dict)


class RuleIn(RuleBase):
    pass


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_code: str
    rule_name: str
    threshold: dict


class RulePatch(BaseModel):
    rule_name: str | None = None
    threshold: dict | None = None
    status: str | None = None
