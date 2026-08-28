"""单据/明细/附件 schema。"""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LineItemIn(BaseModel):
    item_type: str = "expense"
    item_name: str = ""
    expense_date: Optional[date] = None
    expense_location: str = ""
    quantity: float = 1
    unit_price: float = 0
    amount: float = 0
    remark: str = ""


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_type: str
    item_name: str
    expense_date: Optional[date] = None
    expense_location: str
    quantity: float
    unit_price: float
    amount: float
    remark: str


class DocumentIn(BaseModel):
    document_type: str
    applicant_department: str = ""
    budget_department: str = ""
    payee_name: str = ""
    payee_account: str = ""
    expense_category: str = ""
    total_amount: float = 0
    currency: str = "CNY"
    apply_date: Optional[date] = None
    reason_text: str = ""
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    line_items: list[LineItemIn] = Field(default_factory=list)


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_name: str
    file_type: str
    file_size: int
    storage_status: str
    parse_status: str
    created_at: datetime


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_no: int
    document_snapshot_json: dict
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_type: str
    document_no: str
    applicant_id: int
    applicant_department: str
    budget_department: str
    payee_name: str
    payee_account: str
    expense_category: str
    total_amount: float
    currency: str
    apply_date: Optional[date] = None
    reason_text: str
    document_status: str
    current_version: int
    extra_fields: dict
    line_items: list[LineItemOut] = []
    attachments: list[AttachmentOut] = []
    created_at: datetime
    updated_at: datetime


class DocumentListItem(DocumentOut):
    pass
