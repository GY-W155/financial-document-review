"""SQLAlchemy 异步 ORM 模型 —— 对应 2.7.10 全部数据表。

类型特定补充字段（合同编号/付款比例/出差地点等）统一存入
financial_documents.extra_fields_json，满足 2.7.2 五类单据差异需求。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base

# 统一状态常量（2.7.12）
DOC_STATUS = {
    "draft", "pending_review", "reviewing", "returned",
    "approved", "rejected", "withdrawn", "voided",
}
TASK_STATUS = {
    "queued", "querying_document", "loading_attachments",
    "parsing_attachments", "analyzing", "succeeded", "failed", "cancelled",
}
PARSE_STATUS = {"pending", "parsing", "succeeded", "failed", "manual_review"}
REVIEW_STATUS = {"pending", "confirmed", "dismissed"}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    roles: Mapped[list[Role]] = relationship("Role", secondary="user_roles", lazy="selectin")


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    permission_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    permission_name: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), default="")
    action_type: Mapped[str] = mapped_column(String(32), default="")


class UserRole(Base):
    __tablename__ = "user_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"), index=True
    )
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_perm"),)


class ReviewSession(TimestampMixin, Base):
    __tablename__ = "review_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    document_no: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_status: Mapped[str] = mapped_column(String(32), default="ongoing")
    confirmed_slots: Mapped[dict] = mapped_column(JSON, default=dict)  # 已确认槽位


class SessionMessage(Base):
    __tablename__ = "session_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("review_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinancialDocument(TimestampMixin, Base):
    __tablename__ = "financial_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    document_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    applicant_department: Mapped[str] = mapped_column(String(64), default="")
    budget_department: Mapped[str] = mapped_column(String(64), default="")
    payee_name: Mapped[str] = mapped_column(String(128), default="")
    payee_account: Mapped[str] = mapped_column(String(64), default="")
    expense_category: Mapped[str] = mapped_column(String(64), default="")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    apply_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reason_text: Mapped[str] = mapped_column(Text, default="")
    document_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    extra_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)  # 类型特定字段
    version_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    line_items: Mapped[list[DocumentLineItem]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )
    attachments: Mapped[list[DocumentAttachment]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )


class DocumentVersion(TimestampMixin, Base):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    document_snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version"),)


class DocumentLineItem(Base):
    __tablename__ = "document_line_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    item_type: Mapped[str] = mapped_column(String(32), default="expense")  # expense/payment
    item_name: Mapped[str] = mapped_column(String(128), default="")
    expense_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expense_location: Mapped[str] = mapped_column(String(128), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str] = mapped_column(String(255), default="")
    document: Mapped[FinancialDocument] = relationship(back_populates="line_items")


class DocumentAttachment(Base):
    __tablename__ = "document_attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    document_version: Mapped[int] = mapped_column(Integer, default=1)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)  # pdf/png/jpg
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    file_hash: Mapped[str] = mapped_column(String(64), default="")
    storage_status: Mapped[str] = mapped_column(String(16), default="stored")
    parse_status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    document: Mapped[FinancialDocument] = relationship(back_populates="attachments")
    parse_result: Mapped[Optional[AttachmentParseResult]] = relationship(
        back_populates="attachment", uselist=False, cascade="all, delete-orphan",
        lazy="selectin",
    )


class AttachmentParseResult(Base):
    __tablename__ = "attachment_parse_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("document_attachments.id"), unique=True, index=True
    )
    document_category: Mapped[str] = mapped_column(String(32), default="")  # 发票/合同/行程单...
    full_text: Mapped[str] = mapped_column(Text, default="")
    fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_positions_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    attachment: Mapped[DocumentAttachment] = relationship(back_populates="parse_result")


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("document_attachments.id"), index=True)
    invoice_code: Mapped[str] = mapped_column(String(64), default="")
    invoice_no: Mapped[str] = mapped_column(String(64), default="")
    seller_name: Mapped[str] = mapped_column(String(128), default="")
    buyer_name: Mapped[str] = mapped_column(String(128), default="")
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount_excluding_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount_including_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")


class ApprovalWorkflow(TimestampMixin, Base):
    __tablename__ = "approval_workflows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_name: Mapped[str] = mapped_column(String(128), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    match_conditions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")
    nodes: Mapped[list[ApprovalWorkflowNode]] = relationship(
        back_populates="workflow", lazy="selectin", cascade="all, delete-orphan",
        order_by="ApprovalWorkflowNode.node_order",
    )


class ApprovalWorkflowNode(Base):
    __tablename__ = "approval_workflow_nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("approval_workflows.id"), index=True)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    node_order: Mapped[int] = mapped_column(Integer, default=1)
    approver_role: Mapped[str] = mapped_column(String(32), nullable=False)  # 角色 code
    approval_mode: Mapped[str] = mapped_column(String(16), default="any")  # any/all/amount
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    workflow: Mapped[ApprovalWorkflow] = relationship(back_populates="nodes")


class ApprovalInstance(Base):
    __tablename__ = "approval_instances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("approval_workflows.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    document_version: Mapped[int] = mapped_column(Integer, default=1)
    instance_status: Mapped[str] = mapped_column(String(32), default="running")
    current_node_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tasks: Mapped[list[ApprovalTask]] = relationship(
        back_populates="instance", lazy="selectin", cascade="all, delete-orphan"
    )


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("approval_instances.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("approval_workflow_nodes.id"), index=True)
    approver_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    task_status: Mapped[str] = mapped_column(String(32), default="pending")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    instance: Mapped[ApprovalInstance] = relationship(back_populates="tasks")


class DocumentStatusLog(Base):
    __tablename__ = "document_status_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("review_sessions.id"), nullable=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    task_status: Mapped[str] = mapped_column(String(32), default="queued")
    current_step: Mapped[str] = mapped_column(String(64), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[list[RiskFinding]] = relationship(
        back_populates="task", lazy="selectin", cascade="all, delete-orphan"
    )


class RiskFinding(Base):
    __tablename__ = "risk_findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_tasks.id"), index=True)
    risk_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    risk_title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    actual_value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reference_value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    threshold_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    suggestion_text: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    task: Mapped[AnalysisTask] = relationship(back_populates="findings")


class ReviewReport(Base):
    __tablename__ = "review_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("analysis_tasks.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("financial_documents.id"), index=True)
    overall_risk_level: Mapped[str] = mapped_column(String(16), default="low")
    risk_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    amount_comparison_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(String(32), default="manual_review")
    report_markdown: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    manual_reviews: Mapped[list[ManualReview]] = relationship(
        back_populates="report", lazy="selectin", cascade="all, delete-orphan"
    )


class MarketPriceReference(Base):
    __tablename__ = "market_price_references"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    specification: Mapped[str] = mapped_column(String(128), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    price_min: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    price_max: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    source_name: Mapped[str] = mapped_column(String(128), default="")
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    credit_status: Mapped[str] = mapped_column(String(32), default="normal")
    blacklist_status: Mapped[str] = mapped_column(String(16), default="normal")
    risk_tags_json: Mapped[list] = mapped_column(JSON, default=list)
    bank_accounts_json: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ManualReview(Base):
    __tablename__ = "manual_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("review_reports.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    review_result: Mapped[str] = mapped_column(String(32), default="approved")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    report: Mapped[ReviewReport] = relationship(back_populates="manual_reviews")


class AuditRule(TimestampMixin, Base):
    """审核规则参数配置（金额容差/费用标准/市场价区间/异常阈值/供应商规则）。"""

    __tablename__ = "audit_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(64), default="")
    threshold: Mapped[dict] = mapped_column(JSON, default=dict)  # 阈值/标准/区间
    status: Mapped[str] = mapped_column(String(16), default="active")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# 常用复合索引
Index("ix_doc_type_status", FinancialDocument.document_type, FinancialDocument.document_status)
Index("ix_line_item_document", DocumentLineItem.document_id, DocumentLineItem.item_type)
