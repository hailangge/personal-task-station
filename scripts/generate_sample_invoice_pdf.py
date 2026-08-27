"""Generate the sample electronic invoice PDF used by parser tests.

Dev-time helper (requires ``reportlab``, not a runtime dependency):

    .venv/bin/python scripts/generate_sample_invoice_pdf.py

Output: ``fixtures/sample_invoice.pdf`` with layout keywords that real 数电票/
普票 PDFs carry, so ``InvoicePdfEmailParser`` can be exercised end to end.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_pdf(output: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    c = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    lines = [
        "电子发票（普通发票）",
        "发票代码：044032600211   发票号码：24312000000012345678",
        "开票日期：2026年07月15日",
        "购买方信息：",
        "名 称：个人",
        "统一社会信用代码/纳税人识别号：-",
        "项目名称    规格型号    数量    单价    金额    税率",
        "*信息技术服务*软件服务费 1 99.00 99.00 1%",
        "合 计 ¥99.00",
        "价税合计（大写）玖拾玖元整 （小写）¥100.00",
        "销售方信息：",
        "名 称：示例科技服务有限公司",
        "统一社会信用代码/纳税人识别号：91440300TESTCODE0X",
    ]
    y = height - 80
    for line in lines:
        c.setFont("STSong-Light", 11)
        c.drawString(60, y, line)
        y -= 28
    c.save()


def main() -> int:
    output = REPO_ROOT / "fixtures" / "sample_invoice.pdf"
    build_pdf(output)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
