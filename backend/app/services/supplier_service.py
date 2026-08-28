"""供应商服务：档案、风险、历史交易。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FinancialDocument, SupplierProfile


async def get_supplier_risk(db: AsyncSession, supplier_code: str) -> dict | None:
    sup = (await db.execute(select(SupplierProfile).where(
        SupplierProfile.supplier_code == supplier_code))).scalar_one_or_none()
    if not sup:
        return None

    # 历史付款（已通过单据）
    result = await db.execute(select(FinancialDocument).where(
        FinancialDocument.payee_name == sup.supplier_name,
        FinancialDocument.document_status == "approved",
    ).order_by(FinancialDocument.apply_date))
    history = [{"document_no": d.document_no, "amount": float(d.total_amount or 0),
                "apply_date": d.apply_date.isoformat() if d.apply_date else None,
                "currency": d.currency} for d in result.scalars().all()]

    return {
        "supplier_code": sup.supplier_code,
        "supplier_name": sup.supplier_name,
        "credit_status": sup.credit_status,
        "blacklist_status": sup.blacklist_status,
        "risk_tags": sup.risk_tags_json or [],
        "bank_accounts": sup.bank_accounts_json or [],
        "history": history,
        "history_count": len(history),
        "history_total": round(sum(float(h["amount"]) for h in history), 2),
    }
