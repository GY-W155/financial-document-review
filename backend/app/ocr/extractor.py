"""文档文本抽取：PDF 用 pymupdf，图片用 PaddleOCR / LLM 视觉，均懒加载、可降级。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pdf_text(path: str) -> str:
    """提取 PDF 全文文本。"""
    import fitz  # pymupdf 懒导入

    doc = fitz.open(path)
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)


def extract_image_text_ocr(path: str) -> str:
    """使用 PaddleOCR 识别图片文字。若未安装 OCR_ENABLED=False 则抛出。"""
    from ..config import settings

    if not settings.OCR_ENABLED:
        raise RuntimeError("OCR_ENABLED=False，未启用 PaddleOCR")
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:  # 未安装
        raise RuntimeError("paddleocr 未安装") from exc

    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    result = ocr.ocr(path, cls=True)
    lines: list[str] = []
    if not result:
        return ""
    for page_lines in result:
        if not page_lines:
            continue
        for item in page_lines:
            # item: [box, (text, conf)]
            if len(item) >= 2 and isinstance(item[1], (list, tuple)) and len(item[1]) >= 1:
                lines.append(str(item[1][0]))
    return "\n".join(lines)


def file_readable(path: str) -> bool:
    return Path(path).exists() and Path(path).stat().st_size > 0


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}


def is_pdf(path: str) -> bool:
    return Path(path).suffix.lower() == ".pdf"
