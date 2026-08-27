from __future__ import annotations

import io
import zipfile
from decimal import Decimal

import pytest

from personal_task_station.server.importers.email.attachments import extract_csv_members
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parsers.alipay_bill_zip import (
    AlipayBillZipParser,
)
from personal_task_station.server.importers.email.parsers.invoice_pdf import (
    InvoicePdfEmailParser,
)
from personal_task_station.server.importers.email.parsers.wechat_bill_zip import (
    WechatBillZipParser,
)


def _zip_bytes(files: dict[str, str], password: str | None = None) -> bytes:
    buf = io.BytesIO()
    if password is None:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    pyzipper = pytest.importorskip("pyzipper")
    with pyzipper.AESZipFile(buf, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(password.encode())
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _email(subject: str, attachments: list[tuple[str, bytes]], from_addr: str = "") -> FetchedEmail:
    return FetchedEmail(
        uid="1",
        subject=subject,
        from_addr=from_addr,
        date="2026-08-01",
        body_html="",
        body_text="",
        attachments=attachments,
    )


WECHAT_CSV = "\n".join(
    [
        "微信支付账单明细",
        "----------------------",
        "微信昵称：[xxx]",
        "------------------------------",
        "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注",
        "2026-07-01 12:00:00,商户消费,全家便利店,早餐,支出,25.50,零钱,支付成功,1000120260701A,,",
        "2026-07-02 09:00:00,微信红包,李四,红包,收入,88.00,零钱,已存入零钱,1000120260702B,,",
        "2026-07-03 09:00:00,零钱充值,零钱,充值,/,100.00,工商银行(1234),已存入零钱,1000120260703C,,",
    ]
)

ALIPAY_CSV_GBK = "\n".join(
    [
        "支付宝交易记录明细查询",
        "账号:[mock@example.com]",
        "-------------------------------------",
        "交易号,商家订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,交易对方,商品名称,金额（元）,收/支,交易状态,服务费（元）,成功退款（元）,备注,资金状态",
        "2026071522001400001,PO20260715,2026-07-15 10:30:00,2026-07-15 10:30:05,2026-07-15 10:30:06,手机,交易,示例科技服务有限公司,软件服务费,100.00,支出,交易成功,0.00,0.00,,已支出",
        "2026071622001400002,PO20260716,2026-07-16 11:00:00,2026-07-16 11:00:04,2026-07-16 11:00:05,电脑,退款,淘宝网,退货退款,59.90,收入,退款成功,0.00,0.00,,已收入",
    ]
).encode("gbk")


class TestWechatBillZipParser:
    def test_parses_official_csv_rows_and_skips_neutral(self):
        payload = _zip_bytes({"微信支付交易明细证明(20260701-20260731).csv": WECHAT_CSV})
        email = _email("微信支付账单明细", [("bills.zip", payload)], from_addr="service@tenpay.com")
        parser = WechatBillZipParser()
        assert parser.can_parse(email)
        result = parser.parse(email, passwords=())
        assert result.errors == []
        assert len(result.raw_transactions) == 2

        first = result.raw_transactions[0]
        assert first.source_name == "wechat_bill_zip"
        assert first.amount == Decimal("25.50")
        assert first.direction.value == "expense"
        assert first.merchant_name == "全家便利店"
        assert first.external_id == "1000120260701A"
        assert first.channel == "零钱"

        second = result.raw_transactions[1]
        assert second.direction.value == "income"

    def test_wrong_password_reports_error(self):
        payload = _zip_bytes({"b.csv": WECHAT_CSV}, password="correct-horse")
        email = _email("微信支付账单明细", [("bills.zip", payload)])
        result = WechatBillZipParser().parse(email, passwords=("other",))
        assert result.raw_transactions == []
        assert any("wrong or missing password" in err for err in result.errors)

    def test_encrypted_zip_with_matching_password(self):
        payload = _zip_bytes({"加密账单.csv": WECHAT_CSV}, password="secret-password")
        email = _email("微信支付账单明细", [("bills.zip", payload)])
        result = WechatBillZipParser().parse(email, passwords=("secret-password",))
        assert len(result.raw_transactions) == 2


class TestAlipayBillZipParser:
    def test_parses_gbk_csv_rows(self):
        payload = _zip_bytes({"alipay_record_202607.csv": ALIPAY_CSV_GBK.decode("gbk")})
        email = _email("支付宝交易流水证明", [("bill.zip", payload)], from_addr="service@mail.alipay.com")
        parser = AlipayBillZipParser()
        assert parser.can_parse(email)
        result = parser.parse(email, passwords=())
        assert result.errors == []
        assert len(result.raw_transactions) == 2

        expense = result.raw_transactions[0]
        assert expense.amount == Decimal("100.00")
        assert expense.direction.value == "expense"
        assert expense.merchant_name == "示例科技服务有限公司"
        assert expense.external_id == "2026071522001400001"

        refund = result.raw_transactions[1]
        assert refund.direction.value == "income"


class TestAttachmentsModule:
    def test_extracts_utf8_members_only(self):
        payload = _zip_bytes(
            {
                "readme.txt": "not csv",
                "data.csv": "a,b\n1,2\n",
            }
        )
        members, errors = extract_csv_members(payload, ())
        assert errors == []
        assert members == [("data.csv", "a,b\n1,2\n")]

    def test_invalid_zip_reports_error(self):
        members, errors = extract_csv_members(b"not a zip", ())
        assert members == []
        assert errors and "invalid zip archive" in errors[0]


class TestInvoicePdfParser:
    def test_parses_sample_invoice_pdf(self):
        from pathlib import Path

        payload = Path("fixtures/sample_invoice.pdf").read_bytes()
        email = _email("您的电子发票已开具", [("invoice.pdf", payload)], from_addr="invoice@jd.com")
        parser = InvoicePdfEmailParser()
        assert parser.can_parse(email)
        result = parser.parse(email)
        assert result.errors == []
        assert len(result.raw_transactions) == 1
        tx = result.raw_transactions[0]
        assert tx.amount == Decimal("100.00")
        assert tx.direction.value == "expense"
        assert tx.merchant_name == "示例科技服务有限公司"
        assert tx.external_id == "invoice:24312000000012345678"
        assert tx.occurred_on.isoformat() == "2026-07-15"


class TestBillRelatedGate:
    def test_subject_keyword_passes_without_attachment(self):
        from personal_task_station.server.importers.email.service import EmailImportService

        email = _email("招行信用卡账单提醒", [])
        assert EmailImportService.is_bill_related(email) is True

    def test_non_bill_email_is_rejected(self):
        from personal_task_station.server.importers.email.service import EmailImportService

        email = _email("周末大促销快来抢购", [], from_addr="marketing@jd.com")
        assert EmailImportService.is_bill_related(email) is False

    def test_finance_sender_with_zip_attachment_passes(self):
        from personal_task_station.server.importers.email.service import EmailImportService

        email = _email("您的账户资料", [("bill.zip", b"PK")], from_addr="service@mail.alipay.com")
        assert EmailImportService.is_bill_related(email) is True
