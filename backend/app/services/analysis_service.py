"""智能分析服务：汇聚上下文 → 跑规则 → 生成风险项与报告。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import llm_available, summarize_risk
from ..models import (
    AnalysisTask,
    AuditRule,
    DocumentAttachment,
    FinancialDocument,
    InvoiceRecord,
    MarketPriceReference,
    ReviewReport,
    RiskFinding,
    SupplierProfile,
)
from ..rules.engine import (
    AnalysisContext, overall_level, recommendation_for, run_rules,
)
from ..utils.helpers import to_float
from .audit import log_action
from .permissions import assert_can_view_document


async def create_analysis_task(db: AsyncSession, doc: FinancialDocument, session_id: int | None) -> AnalysisTask:
    task = AnalysisTask(session_id=session_id, document_id=doc.id,
                        task_status="queued", current_step="init", progress=0)
    db.add(task)
    await db.flush()
    return task


async def update_task(task: AnalysisTask, status: str, step: str, progress: int, db: AsyncSession | None = None):
    task.task_status = status
    task.current_step = step
    task.progress = progress
    if status in {"succeeded", "failed", "cancelled"}:
        task.finished_at = datetime.utcnow()
    if db:
        await db.commit()


async def load_context(db: AsyncSession, task: AnalysisTask) -> AnalysisContext:
    doc = (await db.execute(select(FinancialDocument).where(
        FinancialDocument.id == task.document_id))).scalar_one()

    # 附件解析结果
    parse_results, invoice_records = [], []
    attachments = doc.attachments
    for att in attachments:
        if att.parse_result:
            parse_results.append(att.parse_result)
    if attachments:
        ids = [a.id for a in attachments]
        inv = await db.execute(select(InvoiceRecord).where(
            InvoiceRecord.attachment_id.in_(ids)))
        invoice_records = list(inv.scalars().all())

    # 规则配置
    rules: dict[str, dict] = {}
    for r in (await db.execute(select(AuditRule).where(AuditRule.status == "active"))).scalars().all():
        rules[r.rule_code] = dict(r.threshold or {})

    # 市场价
    market_prices = list((await db.execute(select(MarketPriceReference))).scalars().all())

    # 供应商匹配
    supplier = None
    if doc.payee_name or doc.payee_account:
        sup = await db.execute(select(SupplierProfile).where(
            (SupplierProfile.supplier_name == doc.payee_name)
            | (SupplierProfile.supplier_code == doc.extra_fields_json.get("supplier_code", ""))
        ))
        supplier = sup.scalars().first()

    # 供应商历史付款（已通过单据，同收款方）
    history = []
    supplier_name = doc.payee_name or ""
    if supplier_name:
        old = await db.execute(select(FinancialDocument).where(
            FinancialDocument.payee_name == supplier_name,
            FinancialDocument.document_status == "approved",
            FinancialDocument.id != doc.id,
        ))
        history = [float(d.total_amount or 0) for d in old.scalars().all()]

    return AnalysisContext(
        document=doc, line_items=doc.line_items, attachments=attachments,
        parse_results=parse_results, invoice_records=invoice_records, rules=rules,
        market_prices=market_prices, supplier=supplier, supplier_history=history,
    )


async def run_analysis(db: AsyncSession, task: AnalysisTask) -> dict:
    """执行分析主流程。返回 {overall_level, findings, report_id}。"""
    await update_task(task, "querying_document", "查询单据", 10, db)
    ctx = await load_context(db, task)

    await update_task(task, "loading_attachments", "加载附件", 30, db)
    await update_task(task, "analyzing", "规则分析与风险汇聚", 60, db)

    raw_findings = run_rules(ctx)
    findings = []
    for f in raw_findings:
        finding = RiskFinding(
            task_id=task.id,
            risk_type=f["risk_type"], risk_level=f["risk_level"], risk_title=f["risk_title"],
            description=f["description"],
            actual_value_json=f.get("actual_value", {}),
            reference_value_json=f.get("reference_value", {}),
            threshold_json=f.get("threshold", {}),
            evidence_json=f.get("evidence", {}),
            suggestion_text=f.get("suggestion_text", ""),
            review_status="pending",
        )
        db.add(finding)
        findings.append(finding)
    await db.flush()

    level = overall_level(raw_findings)
    recommendation = recommendation_for(level)
    amount_comparison = build_amount_comparison(ctx)

    # LLM 建议（可选）
    llm_advice = await summarize_risk([{
        "title": f["risk_title"], "level": f["risk_level"], "desc": f["description"],
    } for f in raw_findings])

    report = ReviewReport(
        task_id=task.id, document_id=ctx.document.id, overall_risk_level=level,
        risk_summary_json={"finding_count": len(raw_findings),
                           "high": sum(1 for f in raw_findings if f["risk_level"] == "high"),
                           "medium": sum(1 for f in raw_findings if f["risk_level"] == "medium"),
                           "low": sum(1 for f in raw_findings if f["risk_level"] == "low"),
                           "llm_advice": llm_advice},
        amount_comparison_json=amount_comparison,
        recommendation=recommendation,
        report_markdown=build_report_markdown(ctx, raw_findings, level, recommendation, amount_comparison),
    )
    db.add(report)
    await db.flush()
    await update_task(task, "succeeded", "分析完成", 100)
    await log_action(db, None, "analysis.run", "analysis_task", task.id,
                     {"overall_level": level, "findings": len(raw_findings)})
    await db.commit()
    return {"overall_level": level, "findings": len(raw_findings), "report_id": report.id}


def build_amount_comparison(ctx: AnalysisContext) -> dict:
    doc_total = ctx.total_amount
    line_total = sum(to_float(i.amount) or 0 for i in ctx.line_items)
    invoice_total = sum(to_float(r.amount_including_tax) or 0 for r in ctx.invoice_records)
    extra = ctx.document.extra_fields_json or {}
    contract_total = to_float(extra.get("contract_amount"))
    pay_amount = doc_total
    return {
        "document_total": doc_total,
        "line_total": round(line_total, 2),
        "invoice_total": round(invoice_total, 2),
        "contract_total": contract_total,
        "payment_total": pay_amount,
        "diffs": {
            "line_vs_document": round(line_total - doc_total, 2),
            "invoice_vs_document": round(invoice_total - doc_total, 2),
            "contract_vs_payment": round((contract_total or 0) - pay_amount, 2),
        },
    }


def build_report_markdown(ctx: AnalysisContext, findings: list[dict], level: str,
                          recommendation: str, comparison: dict) -> str:
    doc = ctx.document
    lines = [
        f"# 财务单据风险审核报告",
        f"**单据编号**：{doc.document_no}　**类型**：{doc.document_type}　**申请人**：{doc.applicant_id}",
        f"**总金额**：{comparison['document_total']}　**附件数**：{len(ctx.attachments)}",
        "",
        f"## 整体风险等级：**{level.upper()}**",
        f"**审核建议**：{recommendation}",
        "",
        "## 金额核对",
        f"- 单据总金额：`{comparison['document_total']}`",
        f"- 明细合计：`{comparison['line_total']}`（差异 `{comparison['diffs']['line_vs_document']}`）",
        f"- 发票合计：`{comparison['invoice_total']}`（差异 `{comparison['diffs']['invoice_vs_document']}`）",
        "",
        "## 风险项列表",
    ]
    if not findings:
        lines.append("- 未发现显著风险项。")
    for i, f in enumerate(findings, 1):
        lines.append(
            f"{i}. **[{f['risk_level'].upper()}]** {f['risk_title']}\n"
            f"   - 描述：{f['description']}\n"
            f"   - 处理建议：{f.get('suggestion_text', '')}"
        )
    lines.append("")
    lines.append("> 本报告由系统规则引擎自动生成，结果仅供审批辅助，最终结论由人工确认。")
    return "\n".join(lines)


async def get_task(db: AsyncSession, task_id: int) -> AnalysisTask:
    task = (await db.execute(select(AnalysisTask).where(AnalysisTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise ValueError("分析任务不存在")
    return task


def findings_to_out(findings: list[RiskFinding]) -> list[dict]:
    return [{
        "id": f.id, "task_id": f.task_id, "risk_type": f.risk_type, "risk_level": f.risk_level,
        "risk_title": f.risk_title, "description": f.description,
        "actual_value": f.actual_value_json, "reference_value": f.reference_value_json,
        "threshold": f.threshold_json, "evidence": f.evidence_json,
        "suggestion_text": f.suggestion_text, "review_status": f.review_status,
        "created_at": f.created_at,
    } for f in findings]
