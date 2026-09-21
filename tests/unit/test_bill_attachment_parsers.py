from __future__ import annotations

import base64
import io
import zipfile
from datetime import date
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


class TestRealWorldStatementStructures:
    """Regression tests derived from live QQ-mail statement samples."""

    CMB_HTML = "\n".join(
        [
            "<html><body>尊敬的客户，您的个人消费卡账单如下：",
            "<table><tr><td>2026/07/16-2026/08/15</td></tr></table>",
            "积分兑换率表 ¥ 41,000.00 其他内容",
            "<table>",
            "<tr><td>消费</td><td>0726</td><td>0727</td><td>财付通-历城区正鑫家电维修经营部</td><td>¥ 100.00</td><td>4957</td><td>CN</td><td>100.00</td></tr>",
            "<tr><td>0726</td><td>0727</td><td>财付通-拼多多平台商户</td><td>¥ 57.76</td><td>4957</td><td>CN</td><td>57.76</td></tr>",
            "<tr><td>还款</td><td>0805</td><td>0806</td><td>财付通-还款渠道</td><td>¥ -1.72</td><td>4957</td><td>CN</td><td>-1.72</td></tr>",
            "<tr><td>0415</td><td>0416</td><td>财付通-分期扣款计划行</td><td>¥ 49.00</td><td>4957</td><td>CN</td><td>49.00</td></tr>",
            "</table></body></html>",
        ]
    )

    def test_cmb_line_scan_handles_rowspan_groups_and_period(self):
        from personal_task_station.server.importers.email.parsers.cmb import CmbEmailParser

        email = _email(
            "招商银行信用卡电子账单", [], from_addr="ccsvc@message.cmbchina.com"
        )
        email.body_html = self.CMB_HTML
        parser = CmbEmailParser()
        assert parser.can_parse(email)
        result = parser.parse(email)
        assert result.errors == []
        # Period 07/16-08/15 keeps 0726/0727/0805 transactions; the 0415
        # installment-plan line and ¥0.00-style markers are excluded.
        amounts = sorted((str(t.amount), t.direction.value) for t in result.raw_transactions)
        assert amounts == [
            ("1.72", "income"),
            ("100.00", "expense"),
            ("57.76", "expense"),
        ]
        assert all(t.card_last4 == "4957" for t in result.raw_transactions)
        assert all(t.external_id.startswith("cmb:") for t in result.raw_transactions)

    def test_bankcomm_cny_amount_cell_and_direction(self):
        from personal_task_station.server.importers.email.parsers.bankcomm import (
            BankcommEmailParser,
        )

        html = "\n".join(
            [
                "<html><body><table>",
                "<tr><td>交易 日期 Transaction Date</td><td>记账 日期</td><td>卡末 四位</td><td>交易 说明 Description</td><td>交易 金额 Transaction Currency</td></tr>",
                "<tr><td>07/29</td><td>07/29</td><td>7352</td><td>消费 （特约）美团</td><td>CNY 24.89</td></tr>",
                "<tr><td>07/27</td><td>07/27</td><td>7352</td><td>信用卡还款 跨行自助转账还款</td><td>CNY 487.57</td></tr>",
                "<tr><td>08/06</td><td>08/06</td><td>7352</td><td>退货 （特约）美团</td><td>CNY 1415.00</td></tr>",
                "</table></body></html>",
            ]
        )
        email = _email(
            "交通银行个人信用卡2026年08月电子账单", [], from_addr="pccc@bocomcc.com"
        )
        email.body_html = html
        parser = BankcommEmailParser()
        assert parser.can_parse(email)
        result = parser.parse(email)
        assert result.errors == []
        assert len(result.raw_transactions) == 3
        by_dir: dict[str, list[str]] = {}
        for tx in result.raw_transactions:
            by_dir.setdefault(tx.direction.value, []).append(str(tx.amount))
        assert by_dir["expense"] == ["24.89"]
        assert sorted(by_dir["income"]) == ["1415.00", "487.57"]
        # Description prefixes stripped, repayment keyword keeps income.
        merchants = {t.merchant_name for t in result.raw_transactions}
        assert "美团" in merchants

    def test_gbk_single_part_html_is_decoded(self):
        """BOComm sends single-part GBK HTML; the client must honor charset."""
        from email import message_from_bytes

        from personal_task_station.server.importers.email.client import (
            EmailClient,
            ImapConfig,
        )

        html = (
            '<html><head><meta http-equiv="Content-Type" content="text/html; '
            'charset=gbk"></head><body>交通银行电子账单 交易日期 金额</body></html>'
        )
        msg = message_from_bytes(
            b"Content-Type: text/html; charset=gbk\r\n"
            b"Content-Transfer-Encoding: base64\r\n\r\n"
            + base64.b64encode(html.encode("gbk"))
        )
        client = EmailClient(ImapConfig(host="imap.qq.com"))
        parsed = client._parse_message("1", msg)
        assert "交通银行电子账单" in parsed.body_html
        assert "交易日期" in parsed.body_html
