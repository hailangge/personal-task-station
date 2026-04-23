from __future__ import annotations

from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parsers import (
    AlipayEmailParser,
    CmbEmailParser,
    GenericNotificationParser,
    JdEmailParser,
    PddEmailParser,
    TaobaoEmailParser,
    WechatEmailParser,
)
from personal_task_station.shared.enums import BillDirection


def _make_email(subject: str, from_addr: str, html: str = "", text: str = "") -> FetchedEmail:
    return FetchedEmail(
        uid="123",
        subject=subject,
        from_addr=from_addr,
        date="Mon, 23 Apr 2026 10:00:00 +0800",
        body_html=html,
        body_text=text,
        attachments=[],
    )


class TestCmbEmailParser:
    def test_parses_html_table(self):
        html = """
        <table>
            <tr><th>交易日期</th><th>商户名称</th><th>支出金额</th><th>收入金额</th></tr>
            <tr><td>2026-04-20</td><td>星巴克咖啡</td><td>35.00</td><td>-</td></tr>
            <tr><td>2026-04-21</td><td>工资发放</td><td>-</td><td>15000.00</td></tr>
        </table>
        """
        email = _make_email("招商银行信用卡对账单", "creditcard@email.cmbchina.com", html=html)
        parser = CmbEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 2
        assert result.raw_transactions[0].merchant_name == "星巴克咖啡"
        assert result.raw_transactions[0].amount == Decimal("35.00")
        assert result.raw_transactions[0].direction == BillDirection.EXPENSE
        assert result.raw_transactions[1].direction == BillDirection.INCOME
        assert result.raw_transactions[1].amount == Decimal("15000.00")

    def test_parses_text_format(self):
        text = """
        2026-04-20 星巴克咖啡 -35.00
        2026-04-21 工资发放 +15000.00
        """
        email = _make_email("交易提醒", "cmb@email.cmbchina.com", text=text)
        parser = CmbEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 2
        assert result.raw_transactions[0].amount == Decimal("35.00")

    def test_can_parse_matching_sender(self):
        email = _make_email("对账单", "creditcard@email.cmbchina.com")
        assert CmbEmailParser().can_parse(email)

    def test_cannot_parse_unrelated_email(self):
        email = _make_email("广告", "ads@example.com")
        assert not CmbEmailParser().can_parse(email)


class TestAlipayEmailParser:
    def test_parses_payment_notification(self):
        text = """
        付款金额：¥123.45
        商户名称：某某超市
        创建时间：2026-04-23 14:30:00
        交易成功
        """
        email = _make_email("支付成功通知", "service@mail.alipay.com", text=text)
        parser = AlipayEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("123.45")
        assert result.raw_transactions[0].merchant_name == "某某超市"
        assert result.raw_transactions[0].direction == BillDirection.EXPENSE

    def test_parses_refund_notification(self):
        text = "退款金额：¥99.00 商家：某某店铺 退款成功"
        email = _make_email("退款通知", "service@mail.alipay.com", text=text)
        parser = AlipayEmailParser()
        result = parser.parse(email)
        assert result.raw_transactions[0].direction == BillDirection.INCOME


class TestWechatEmailParser:
    def test_parses_payment(self):
        text = "支付金额：¥88.88\n商户：麦当劳\n支付时间：2026-04-23"
        email = _make_email("微信支付凭证", "pay@wechat.com", text=text)
        parser = WechatEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("88.88")
        assert result.raw_transactions[0].merchant_name == "麦当劳"

    def test_parses_income(self):
        text = "金额：¥200.00 零钱到账 交易时间：2026-04-23"
        email = _make_email("入账通知", "service@wechat.com", text=text)
        parser = WechatEmailParser()
        result = parser.parse(email)
        assert result.raw_transactions[0].direction == BillDirection.INCOME


class TestJdEmailParser:
    def test_parses_order(self):
        text = "实付金额：¥2999.00 下单时间：2026-04-22 商品：iPhone 16"
        email = _make_email("订单确认", "service@jd.com", text=text)
        parser = JdEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("2999.00")
        assert "京东" in result.raw_transactions[0].merchant_name


class TestTaobaoEmailParser:
    def test_parses_order(self):
        text = "实付款：¥158.00 成交时间：2026-04-21 店铺：优衣库官方旗舰店"
        email = _make_email("已付款", "no-reply@taobao.com", text=text)
        parser = TaobaoEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("158.00")


class TestPddEmailParser:
    def test_parses_order(self):
        text = "实付金额：¥19.90 下单时间：2026-04-20 店铺：某某水果店"
        email = _make_email("订单", "service@pinduoduo.com", text=text)
        parser = PddEmailParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("19.90")


class TestGenericParser:
    def test_parses_unknown_payment_email(self):
        text = "您已支付 ¥66.60 元 商户：某餐厅 时间：2026-04-23"
        email = _make_email("交易提醒", "unknown@example.com", text=text)
        parser = GenericNotificationParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 1
        assert result.raw_transactions[0].amount == Decimal("66.60")

    def test_falls_back_gracefully(self):
        email = _make_email("广告", "ads@example.com", text="点击领取优惠券")
        parser = GenericNotificationParser()
        result = parser.parse(email)
        assert len(result.raw_transactions) == 0
