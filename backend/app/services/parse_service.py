"""附件解析服务：文本抽取 + 类别识别 + 字段提取 + 证据定位 + 落库。"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..llm import prompts
from ..llm.client import encode_image_base64, extract_json, llm_available
from ..models import AttachmentParseResult, DocumentAttachment, InvoiceRecord
from ..ocr.extractor import (
    extract_image_text_ocr, extract_pdf_text, is_image, is_pdf,
)
from .audit import log_action

logger = logging.getLogger(__name__)


def extract_raw_text(att: DocumentAttachment) -> str:
    path = att.file_path
    if is_pdf(path):
        return extract_pdf_text(path)
    if is_image(path):
        try:
            return extract_image_text_ocr(path)
        except RuntimeError as exc:
            logger.warning("图片 OCR 降级：%s", exc)
            return ""  # 交给 LLM 视觉通道或标记 manual_review
    return ""


async def extract_vision_text(att: DocumentAttachment) -> str:
    """OCR 不可用时，尝试用 LLM 视觉直接识图。"""
    from ..llm.client import chat_vision, llm_available

    if not llm_available():
        return ""
    try:
        data = open(att.file_path, "rb").read()
        mime = "image/png"
        lower = (att.file_name or "").lower()
        if lower.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        return await chat_vision(encode_image_base64(data), prompts.VISION_OCR_PROMPT, mime=mime)
    except Exception as exc:
        logger.warning("LLM 视觉识别失败：%s", exc)
        return ""


async def parse_attachment(db: AsyncSession, attachment: DocumentAttachment) -> dict:
    """执行解析并落库。成功->succeeded；失败->manual_review；空文本->manual_review。"""
    attachment.parse_status = "parsing"
    await db.commit()
    result = None
    try:
        raw_text = extract_raw_text(attachment)
        if not raw_text.strip() and is_image(attachment.file_path):
            raw_text = await extract_vision_text(attachment)

        category, fields, confidence = "未知", {}, 0.0
        if raw_text.strip():
            category, fields, confidence = await extract_fields(raw_text)

        if raw_text.strip():
            result = AttachmentParseResult(
                attachment_id=attachment.id,
                document_category=category,
                full_text=raw_text,
                fields_json=fields,
                evidence_positions_json=[],
                confidence=confidence,
            )
            db.add(result)
            await _save_invoice_record(db, attachment.id, fields)
            attachment.parse_status = "succeeded"
        else:
            attachment.parse_status = "manual_review"
    except Exception as exc:
        logger.exception("附件解析失败")
        attachment.parse_status = "failed"

    await log_action(db, None, "attachment.parse", "attachment", attachment.id,
                     {"parse_status": attachment.parse_status})
    await db.commit()
    return {"attachment_id": attachment.id, "parse_status": attachment.parse_status}


async def extract_fields(text: str) -> tuple[str, dict, float]:
    """调用 LLM 抽取类别与字段；LLM 不可用时走启发式正则回退。"""
    if not llm_available():
        category, fields, _ = _heuristic_extract(text)
        return category, fields, 0.6
    try:
        data = await extract_json([
            {"role": "system", "content": prompts.FIELD_EXTRACT_SYSTEM},
            {"role": "user", "content": prompts.FIELD_EXTRACT_PROMPT.format(
                categories="/".join(prompts.DOCUMENT_CATEGORIES), text=text[:6000])},
        ])
        category = data.get("document_category", "未知")
        if category not in prompts.DOCUMENT_CATEGORIES:
            category = "其他"
        fields = data.get("fields", {}) or {}
        return category, fields, 0.9
    except Exception as exc:
        logger.warning("LLM 字段抽取失败：%s", exc)
        return "未知", {}, 0.0


def _heuristic_extract(text: str) -> tuple[str, dict, float]:
    """无 LLM 时的规则式抽取：类别判定 + 关键字段正则。"""
    import re

    category = "其他"
    for kw, cat in [("发票", "发票"), ("合同", "合同"), ("行程", "行程单"),
                    ("付款", "付款依据"), ("费用明细", "费用明细")]:
        if kw in text:
            category = cat
            break

    def grab(pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    fields = {
        "invoice_code": grab(r"发票代码[:：]?\s*([0-9A-Za-z-]+)"),
        "invoice_no": grab(r"发票号码[:：]?\s*([0-9]+)"),
        "seller_name": grab(r"销售方[（(]?[^：:\n]*[)）][:：]?\s*([^\n]+)") or grab(r"销售方[:：]\s*([^\n]+)"),
        "buyer_name": grab(r"购买方[:：]\s*([^\n]+)"),
        "invoice_date": grab(r"开票日期[:：]\s*(\d{4}-\d{2}-\d{2})"),
        "amount_excluding_tax": grab(r"金额[^0-9]*([0-9]+(?:\.[0-9]+)?)"),
        "tax_amount": grab(r"税额[^0-9]*([0-9]+(?:\.[0-9]+)?)"),
        "amount_including_tax": grab(r"价税合计[^0-9]*([0-9]+(?:\.[0-9]+)?)")
        or grab(r"合计[^0-9]*([0-9]+(?:\.[0-9]+)?)"),
    }
    # 合同补充字段
    fields["contract_no"] = grab(r"合同编号[:：]\s*([A-Za-z0-9-]+)")
    fields["contract_amount"] = grab(r"合同金额[:：]?\s*[¥￥]?\s*([0-9.]+)")
    return category, fields, 0.6


async def _save_invoice_record(db, attachment_id: int, fields: dict) -> None:
    if not fields:
        return
    rec = InvoiceRecord(
        attachment_id=attachment_id,
        invoice_code=str(fields.get("invoice_code") or ""),
        invoice_no=str(fields.get("invoice_no") or ""),
        seller_name=str(fields.get("seller_name") or ""),
        buyer_name=str(fields.get("buyer_name") or ""),
        invoice_date=_parse_date(fields.get("invoice_date")),
        amount_excluding_tax=fields.get("amount_excluding_tax") or 0,
        tax_amount=fields.get("tax_amount") or 0,
        amount_including_tax=fields.get("amount_including_tax") or 0,
        currency="CNY",
    )
    db.add(rec)


def _parse_date(value) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
