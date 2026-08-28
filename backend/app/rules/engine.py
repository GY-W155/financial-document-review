"""规则引擎：纯函数规则，输入 AnalysisContext 输出风险发现列表。

每条规则返回 dict：
{ risk_type, risk_level, risk_title, description, actual_value, reference_value,
  threshold, evidence, suggestion_text }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.helpers import money_equal, percent_diff, to_float

LEVEL_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass
class AnalysisContext:
    document: Any
    line_items: list[Any] = field(default_factory=list)
    attachments: list[Any] = field(default_factory=list)
    parse_results: list[Any] = field(default_factory=list)
    invoice_records: list[Any] = field(default_factory=list)
    rules: dict[str, dict] = field(default_factory=dict)          # rule_code -> threshold
    market_prices: list[Any] = field(default_factory=list)
    supplier: Any = None
    supplier_history: list[Any] = field(default_factory=list)

    # ---- 便捷属性 ----
    @property
    def total_amount(self) -> float:
        return float(self.document.total_amount or 0)

    @property
    def doc_type(self) -> str:
        return self.document.document_type

    def rule(self, code: str) -> dict:
        return self.rules.get(code, {})


def _threshold_of(rule: dict, keys: list[str], default: float) -> float:
    for k in keys:
        if k in rule:
            return to_float(rule[k]) or 0
    return default


# ---------- 规则实现 ----------

def rule_amount_consistency(ctx: AnalysisContext) -> list[dict]:
    """单据与发票金额一致性。"""
    if not ctx.invoice_records:
        return []
    invoice_sum = sum(float(r.amount_including_tax or 0) for r in ctx.invoice_records)
    total = ctx.total_amount
    if invoice_sum == 0:
        return []
    diff = total - invoice_sum
    ratio = percent_diff(total, invoice_sum) or 0
    tolerance = max(_threshold_of(ctx.rule("amount_consistency"), ["amount_tolerance", "tolerance"], 50), 1)
    if abs(diff) <= tolerance:
        return []
    level = "high" if abs(ratio) >= 10 else ("medium" if abs(ratio) >= 5 else "low")
    return [{
        "risk_type": "amount_consistency",
        "risk_level": level,
        "risk_title": "单据金额与发票金额差异",
        "description": f"单据申请金额 {total:.2f} 与发票含税金额合计 {invoice_sum:.2f} 相差 {diff:.2f}（{ratio:.2f}%）",
        "actual_value": {"document_total": total, "invoice_total": invoice_sum, "diff": diff, "diff_ratio": ratio},
        "reference_value": {"invoice_total": invoice_sum},
        "threshold": {"amount_tolerance": tolerance},
        "evidence": {"source_type": "invoice_records", "count": len(ctx.invoice_records)},
        "suggestion_text": "补充与单金额一致的发票或更正单据金额。",
    }]


def rule_line_total_consistency(ctx: AnalysisContext) -> list[dict]:
    """明细与总金额一致性。"""
    items = ctx.line_items
    if not items:
        return []
    sum_amount = sum(float(i.amount or 0) for i in items)
    total = ctx.total_amount
    diff = sum_amount - total
    tolerance = _threshold_of(ctx.rule("line_total_consistency"), ["tolerance"], 10)
    if abs(diff) <= tolerance:
        return []
    level = "high" if abs(diff) > max(total * 0.05, 100) else "medium"
    return [{
        "risk_type": "line_total_consistency",
        "risk_level": level,
        "risk_title": "明细合计与单据总金额不一致",
        "description": f"明细合计 {sum_amount:.2f} 与单据总金额 {total:.2f} 相差 {diff:.2f}",
        "actual_value": {"line_total": sum_amount, "document_total": total, "diff": diff},
        "reference_value": {"document_total": total},
        "threshold": {"tolerance": tolerance},
        "evidence": {"source_type": "line_items", "count": len(items)},
        "suggestion_text": "核对明细是否漏项、重复或金额填报错误。",
    }]


def rule_batch_payment_consistency(ctx: AnalysisContext) -> list[dict]:
    """批量付款一致性：笔数/各笔合计 vs 批次总金额，识别重复收款账号。"""
    if ctx.doc_type != "批量付款单":
        return []
    items = [i for i in ctx.line_items if i.item_type == "payment"]
    if not items:
        return []
    sum_amount = sum(float(i.amount or 0) for i in items)
    total = ctx.total_amount
    findings = []
    if abs(sum_amount - total) > 10:
        findings.append({
            "risk_type": "batch_payment_consistency",
            "risk_level": "medium",
            "risk_title": "批量付款批次金额与明细合计不符",
            "description": f"批次总金额 {total:.2f}，明细合计 {sum_amount:.2f}",
            "actual_value": {"batch_total": total, "sum_amount": sum_amount},
            "reference_value": {"sum_amount": sum_amount},
            "threshold": {"tolerance": 10},
            "evidence": {"source_type": "line_items"},
            "suggestion_text": "核对批量付款明细金额是否漏录或重复。",
        })
    # 重复收款账号（从 extra_fields 的明细集中）
    payees = [s for s in str(ctx.document.extra_fields_json.get("payees") or "").split(",") if s]
    seen = [s for i, s in enumerate(payees) if s in payees[:i]]
    if seen:
        findings.append({
            "risk_type": "batch_payment_consistency",
            "risk_level": "high",
            "risk_title": "批量付款存在重复收款对象",
            "description": f"发现重复收款对象：{','.join(set(seen))}",
            "actual_value": {"duplicates": sorted(set(seen))},
            "reference_value": {},
            "threshold": {},
            "evidence": {"source_type": "extra_fields"},
            "suggestion_text": "确认是否为重复付款，若为同一对象请合并。",
        })
    return findings


def rule_contract_payment_consistency(ctx: AnalysisContext) -> list[dict]:
    """合同与付款一致性：合同金额 vs 付款金额、付款比例。"""
    if ctx.doc_type not in {"对公付款单", "预付款单"}:
        return []
    extra = ctx.document.extra_fields_json or {}
    contract_amount = to_float(extra.get("contract_amount"))
    if contract_amount is None:
        return []
    pay_amount = ctx.total_amount
    ratio_pay = to_float(extra.get("payment_ratio"))
    diff = contract_amount - pay_amount
    findings = []
    if not money_equal(pay_amount, contract_amount, 10):
        findings.append({
            "risk_type": "contract_payment_consistency",
            "risk_level": "medium",
            "risk_title": "付款金额与合同金额不一致",
            "description": f"合同金额 {contract_amount:.2f}，本次付款 {pay_amount:.2f}，差额 {diff:.2f}",
            "actual_value": {"contract_amount": contract_amount, "pay_amount": pay_amount},
            "reference_value": {"contract_amount": contract_amount},
            "threshold": {"tolerance": 10},
            "evidence": {"source_type": "extra_fields"},
            "suggestion_text": "确认是否符合合同约定的付款比例。",
        })
    if ratio_pay is not None and pay_amount > 0:
        # 兼容 0-1 的小数与 0-100 的百分比两种写法
        expected_pct = ratio_pay * 100 if ratio_pay <= 1 else ratio_pay
        actual_ratio = round(pay_amount / contract_amount * 100, 2) if contract_amount else 0
        if abs(actual_ratio - expected_pct) > 5:
            findings.append({
                "risk_type": "contract_payment_consistency",
                "risk_level": "high",
                "risk_title": "实际付款比例与约定不符",
                "description": f"约定付款比例 {expected_pct}%，实际 {actual_ratio}%",
                "actual_value": {"expected_ratio": expected_pct, "actual_ratio": actual_ratio},
                "reference_value": {"expected_ratio": expected_pct},
                "threshold": {"ratio_tolerance": 5},
                "evidence": {"source_type": "extra_fields"},
                "suggestion_text": "核实是否符合合同付款条件。",
            })
    return findings


def rule_market_price(ctx: AnalysisContext) -> list[dict]:
    """市场价格合理性：明细单价 vs 市场价区间。"""
    if not ctx.market_prices:
        return []
    findings = []
    for item in ctx.line_items:
        name = (item.item_name or "").strip()
        if not name:
            continue
        for mp in ctx.market_prices:
            if mp.item_name != name:
                continue
            unit = float(item.unit_price or item.amount or 0)
            pmin, pmax = float(mp.price_min or 0), float(mp.price_max or 0)
            if unit < pmin:
                small_level = "low" if unit >= pmin * 0.8 else "medium"
                findings.append({
                    "risk_type": "market_price",
                    "risk_level": small_level,
                    "risk_title": f"「{name}」单价低于市场价区间",
                    "description": f"单价 {unit:.2f} 低于市场价下限 {pmin:.2f}",
                    "actual_value": {"unit_price": unit},
                    "reference_value": {"price_min": pmin, "price_max": pmax},
                    "threshold": {"price_min": pmin, "price_max": pmax},
                    "evidence": {"source_type": "market_price_references", "item": name},
                    "suggestion_text": "确认是否存在低质或不实报价。",
                })
            elif unit > pmax:
                level = "high" if unit > pmax * 1.3 else "medium"
                ratio = percent_diff(unit, pmax) or 0
                findings.append({
                    "risk_type": "market_price",
                    "risk_level": level,
                    "risk_title": f"「{name}」单价高于市场价区间",
                    "description": f"单价 {unit:.2f}，高于市场价上限 {pmax:.2f}（{ratio:.2f}%）",
                    "actual_value": {"unit_price": unit},
                    "reference_value": {"price_max": pmax},
                    "threshold": {"price_min": pmin, "price_max": pmax},
                    "evidence": {"source_type": "market_price_references", "item": name},
                    "suggestion_text": "要求提供更高规格报价或说明。",
                })
            break
    return findings


def rule_supplier_risk(ctx: AnalysisContext) -> list[dict]:
    """供应商风险：黑名单 / 风险标签 / 高危资质。"""
    if not ctx.supplier:
        return []
    findings = []
    s = ctx.supplier
    tags = s.risk_tags_json or []
    if s.blacklist_status == "blacklisted":
        findings.append({
            "risk_type": "supplier_risk",
            "risk_level": "high",
            "risk_title": "收款供应商在黑名单中",
            "description": f"供应商 {s.supplier_name} 已被列入黑名单",
            "actual_value": {"blacklist_status": s.blacklist_status},
            "reference_value": {},
            "threshold": {},
            "evidence": {"source_type": "supplier_profiles"},
            "suggestion_text": "禁止向黑名单供应商付款，请更换收款方。",
        })
    high_tags = [t for t in tags if t in {"失信", "经营异常", "涉诉", "资质过期"}]
    if high_tags:
        findings.append({
            "risk_type": "supplier_risk",
            "risk_level": "high",
            "risk_title": "供应商存在高风险标签",
            "description": f"风险标签：{','.join(high_tags)}",
            "actual_value": {"risk_tags": tags},
            "reference_value": {},
            "threshold": {},
            "evidence": {"source_type": "supplier_profiles"},
            "suggestion_text": "人工核实供应商经营与涉诉风险。",
        })
    return findings


def rule_attachment_completeness(ctx: AnalysisContext) -> list[dict]:
    """附件完整性：按单据类型必需附件。"""
    required_by_type = {
        "对公付款单": ["发票", "合同", "付款依据"],
        "预付款单": ["发票", "合同", "付款依据"],
        "批量付款单": ["付款依据", "费用明细"],
        "费用报销单": ["发票", "费用明细"],
        "差旅报销单": ["行程单", "发票"],
    }
    required = required_by_type.get(ctx.doc_type, [])
    if not required:
        return []
    have_categories = {p.document_category for p in ctx.parse_results}
    # 无解析结果视为缺失附件
    if not ctx.parse_results and not ctx.attachments:
        return [{
            "risk_type": "attachment_completeness",
            "risk_level": "high",
            "risk_title": "缺少必需附件",
            "description": "未上传任何附件，无法完成关键字段核对",
            "actual_value": {"uploaded": 0},
            "reference_value": {"required": required},
            "threshold": {"required": required},
            "evidence": {"source_type": "attachments"},
            "suggestion_text": "请上传发票、合同、行程单等必需材料。",
        }]
    missing = [c for c in required if c not in have_categories]
    if missing:
        return [{
            "risk_type": "attachment_completeness",
            "risk_level": "medium",
            "risk_title": "附件类别不完整",
            "description": f"缺少类别：{','.join(missing)}",
            "actual_value": {"have": sorted(have_categories), "missing": missing},
            "reference_value": {"required": required},
            "threshold": {"required": required},
            "evidence": {"source_type": "attachment_parse_results"},
            "suggestion_text": f"补交：{','.join(missing)}。",
        }]
    return []


def rule_duplicate_invoice(ctx: AnalysisContext) -> list[dict]:
    """重复票据风险：发票代码+号码+金额+开票日期+销售方。"""
    invoices = ctx.invoice_records
    if len(invoices) < 2:
        return []
    seen: dict[str, list] = {}
    for r in invoices:
        key = f"{r.invoice_code}|{r.invoice_no}|{float(r.amount_including_tax or 0)}|{r.seller_name}"
        seen.setdefault(key, []).append(r)
    findings = []
    for key, group in seen.items():
        if len(group) >= 2:
            findings.append({
                "risk_type": "duplicate_invoice",
                "risk_level": "high",
                "risk_title": "检测到重复发票",
                "description": f"发票 {key.split('|')[0]}|{key.split('|')[1]} 重复提交 {len(group)} 次",
                "actual_value": {"duplicate_count": len(group), "key": key},
                "reference_value": {},
                "threshold": {},
                "evidence": {"source_type": "invoice_records", "key": key},
                "suggestion_text": "确认是否存在一票多报。",
            })
    return findings


def rule_behavior_anomaly(ctx: AnalysisContext) -> list[dict]:
    """消费行为异常（基础版）：金额突增 / 高频。"""
    findings = []
    total = ctx.total_amount
    avg_history = _avg_history_amount(ctx)
    if avg_history and total > avg_history * 3:
        findings.append({
            "risk_type": "behavior_anomaly",
            "risk_level": "high",
            "risk_title": "本次支出金额显著高于历史",
            "description": f"本次 {total:.2f}，历史均值 {avg_history:.2f}，超出 {total/avg_history:.1f} 倍",
            "actual_value": {"current": total, "history_avg": avg_history},
            "reference_value": {"history_avg": avg_history},
            "threshold": {"multiplier": 3},
            "evidence": {"source_type": "supplier_history" if ctx.supplier_history else "history"},
            "suggestion_text": "核实本期支出异常放大的原因。",
        })
    return findings


def _avg_history_amount(ctx: AnalysisContext) -> float:
    amts = [float(x) for x in ctx.supplier_history if x is not None]
    if not amts:
        return 0.0
    return sum(amts) / len(amts)


# ---------- 规则注册表 ----------

REGISTRY: list = [
    rule_amount_consistency,
    rule_line_total_consistency,
    rule_batch_payment_consistency,
    rule_contract_payment_consistency,
    rule_market_price,
    rule_supplier_risk,
    rule_attachment_completeness,
    rule_duplicate_invoice,
    rule_behavior_anomaly,
]


def run_rules(ctx: AnalysisContext) -> list[dict]:
    findings: list[dict] = []
    for fn in REGISTRY:
        try:
            findings.extend(fn(ctx))
        except Exception:  # 单条规则异常不影响整体
            continue
    return findings


def overall_level(findings: list[dict]) -> str:
    if not findings:
        return "low"
    top = max((LEVEL_RANK.get(f.get("risk_level", "low"), 1) for f in findings), default=1)
    high_count = sum(1 for f in findings if f.get("risk_level") == "high")
    if top >= 3:
        return "high"
    if top == 2:
        return "high" if high_count >= 2 else "medium"
    return "low"


def recommendation_for(level: str) -> str:
    if level == "high":
        return "建议驳回"
    if level == "medium":
        return "人工复核"
    return "建议通过"
