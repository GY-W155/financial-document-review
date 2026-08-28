"""生成评估用样例发票 PDF（scripts/samples/invoice_XXX.pdf）。

用 pymupdf 内嵌 CJK 字体，使服务端解析能抽取出中文字段。这些文件是评估脚本的输入。
用法：python scripts/gen_samples.py   （需 pymupdf；评估客户端本身不再需要）
"""
import os

import fitz  # pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(BASE, "scripts", "samples")
os.makedirs(DIR, exist_ok=True)

# amount -> (发票号码, 不含税金额, 税额)
SAMPLES = {
    "1000": ("12345679", "880.00", "120.00"),
    "1017": ("12345678", "900.00", "117.00"),
    "1200": ("12345680", "1100.00", "100.00"),
    "10000": ("12345681", "9000.00", "1000.00"),
}
SELLER = "北京华宇科技有限公司"


def make(amount: int) -> str:
    no, excl, tax = SAMPLES[str(amount)]
    text = (
        f"增值税专用发票\n发票代码 0110\n发票号码 {no}\n销售方 {SELLER}\n"
        f"购买方 某某有限公司\n开票日期 2026-08-01\n金额 {excl}\n税额 {tax}\n价税合计 {amount}.00\n"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="china-s")
    page.insert_text((72, 100), text, fontname="china-s", fontsize=11)
    out = os.path.join(DIR, f"invoice_{amount}.pdf")
    doc.save(out)
    doc.close()
    return out


if __name__ == "__main__":
    for k in SAMPLES:
        print("生成", make(int(k)))
