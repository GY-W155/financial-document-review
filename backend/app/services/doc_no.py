"""单据编号生成。"""
import random
from datetime import datetime

PREFIX = {
    "对公付款单": "DN-PAY",
    "预付款单": "DN-ADV",
    "批量付款单": "DN-BATCH",
    "费用报销单": "DN-EXP",
    "差旅报销单": "DN-TRV",
}
DEFAULT_PREFIX = "DN-DOC"


def generate_document_no(document_type: str, seq: int | None = None) -> str:
    prefix = PREFIX.get(document_type, DEFAULT_PREFIX)
    today = datetime.now().strftime("%Y%m%d")
    if seq is None:
        seq = random.randint(1000, 9999)
    return f"{prefix}-{today}-{seq}"
