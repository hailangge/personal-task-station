from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from personal_task_station.server.importers.alipay_api.client import AlipayBillClient, AlipayConfig
from personal_task_station.shared.enums import BillDirection


def test_csv_row_to_transaction():
    client = AlipayBillClient(
        AlipayConfig(app_id="test", private_key_path="/dev/null", alipay_public_key_path="/dev/null")
    )
    row = {
        "支付宝交易号": "2026042322001156789012345678",
        "商户订单号": "ORDER123456",
        "交易创建时间": "2026-04-23 14:30:00",
        "付款时间": "2026-04-23 14:30:05",
        "最近修改时间": "2026-04-23 14:30:05",
        "交易来源地": "当面付",
        "类型": "交易",
        "交易对方": "星巴克咖啡",
        "商品名称": "拿铁大杯",
        "金额（元）": "35.00",
        "收/支": "支出",
        "交易状态": "成功",
        "服务费（元）": "0.00",
        "成功退款（元）": "0.00",
        "备注": "",
        "资金状态": "已支出",
    }
    tx = client._csv_row_to_transaction(row)
    assert tx is not None
    assert tx.amount == Decimal("35.00")
    assert tx.direction == BillDirection.EXPENSE
    assert tx.merchant_name == "星巴克咖啡"
    assert tx.occurred_on == date(2026, 4, 23)
    assert tx.external_id == "2026042322001156789012345678"
    assert tx.source_name == "alipay_api"


def test_csv_row_income():
    client = AlipayBillClient(
        AlipayConfig(app_id="test", private_key_path="/dev/null", alipay_public_key_path="/dev/null")
    )
    row = {
        "支付宝交易号": "2026042322001156789012345679",
        "交易创建时间": "2026-04-23 10:00:00",
        "交易对方": "张三",
        "商品名称": "转账",
        "金额（元）": "500.00",
        "收/支": "收入",
        "交易状态": "成功",
        "服务费（元）": "0.00",
        "成功退款（元）": "0.00",
        "备注": "",
        "资金状态": "已收入",
    }
    tx = client._csv_row_to_transaction(row)
    assert tx is not None
    assert tx.amount == Decimal("500.00")
    assert tx.direction == BillDirection.INCOME
    assert tx.merchant_name == "张三"


def test_parse_bill_content():
    import io, zipfile

    # Build a minimal Alipay-style CSV inside a ZIP
    csv_lines = [
        "# 支付宝业务明细查询",
        "# 账号：test@example.com",
        "# 起始日期：2026-04-23  终止日期：2026-04-23",
        "支付宝交易号,商户订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,交易对方,商品名称,金额（元）,收/支,交易状态,服务费（元）,成功退款（元）,备注,资金状态",
        "20260423001,ORDER001,2026-04-23 10:00:00,2026-04-23 10:00:01,2026-04-23 10:00:01,手机网站,交易,麦当劳,套餐A,45.50,支出,交易成功,0.00,0.00,,已支出",
        "20260423002,ORDER002,2026-04-23 15:00:00,2026-04-23 15:00:02,2026-04-23 15:00:02,手机网站,交易,工资发放,工资,15000.00,收入,交易成功,0.00,0.00,,已收入",
    ]
    csv_content = "\n".join(csv_lines).encode("utf-8-sig")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("2088002007018916_20260423.csv", csv_content)
    zip_bytes = zip_buffer.getvalue()

    client = AlipayBillClient(
        AlipayConfig(app_id="test", private_key_path="/dev/null", alipay_public_key_path="/dev/null")
    )
    result = client._parse_bill_content(zip_bytes)
    assert len(result.raw_transactions) == 2
    assert result.raw_transactions[0].amount == Decimal("45.50")
    assert result.raw_transactions[0].direction == BillDirection.EXPENSE
    assert result.raw_transactions[1].amount == Decimal("15000.00")
    assert result.raw_transactions[1].direction == BillDirection.INCOME
