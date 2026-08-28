"""LLM prompt 模板与字段提取/OCR 的结构定义。"""

DOCUMENT_CATEGORIES = ["发票", "合同", "行程单", "付款依据", "费用明细", "其他"]

FIELD_EXTRACT_SYSTEM = (
    "你是财务票据信息抽取助手。从给定的票据/合同文本抽取关键字段。"
    "只输出 JSON，不要输出任何解释。字段值不确定的用空字符串。"
)

FIELD_EXTRACT_PROMPT = """请从以下文档文本抽取字段，返回 JSON：
{{
  "document_category": "{categories}",
  "fields": {{
    "invoice_code": "发票代码",
    "invoice_no": "发票号码",
    "seller_name": "销售方名称",
    "buyer_name": "购买方名称",
    "invoice_date": "开票日期(YYYY-MM-DD)",
    "amount_excluding_tax": 不含税金额,
    "tax_amount": 税额,
    "amount_including_tax": 含税金额
  }},
  "contract_no": "合同编号",
  "contract_amount": 合同金额,
  "contract_authority": "合同签署主体"
}}

文档文本：
---
{text}
---
"""

VISION_OCR_PROMPT = (
    "你是财务票据 OCR 专家。请识别图片/票据中的文字，返回全文文本。"
    "若有发票，请务必输出：发票代码、发票号码、销售方、购买方、开票日期、不含税金额、税额、含税金额。"
)

RISK_SUMMARY_PROMPT = """请基于以下风险项总结整体风险结论与处理建议。
最终建议从四类中选一个：建议通过 / 补充材料 / 人工复核 / 建议驳回。

风险项：
---
{risks}
---
"""
