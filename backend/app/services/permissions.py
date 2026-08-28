"""单据权限判定。"""
from fastapi import HTTPException, status

from ..models import FinancialDocument, User


def _roles(user: User) -> set[str]:
    return {r.role_code for r in user.roles}


def assert_can_view_document(user: User, doc: FinancialDocument) -> None:
    """查看权限：本人单据，或 approver/finance/admin 全量。"""
    codes = _roles(user)
    if doc.applicant_id == user.id or codes & {"approver", "finance", "admin"}:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看该单据")


def assert_can_write_document(user: User, doc: FinancialDocument) -> None:
    """写操作权限：仅申请人本人或管理员。"""
    codes = _roles(user)
    if doc.applicant_id == user.id or "admin" in codes:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作该单据")


def is_approver(user: User) -> bool:
    return "approver" in _roles(user) or "admin" in _roles(user)


def is_finance(user: User) -> bool:
    return "finance" in _roles(user) or "admin" in _roles(user)
