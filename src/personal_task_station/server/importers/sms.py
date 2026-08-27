"""Bank dynamic-account SMS parser (银行动账短信).

Handles the common Chinese bank SMS templates, e.g.::

    【招商银行】您尾号1234的账户7月1日12:00完成快捷支付交易人民币100.00元
    【工商银行】您尾号0001卡7月2日入账工资12,000.00元
    【建设银行】向京东商户支付了¥45.00，余额1,234.56元
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from personal_task_station.server.importers.base import RawTransaction
from personal_task_station.shared.enums import BillDirection

_INCOME_PATTERNS = (
    r"(?:入账|到账|存入|转入|收款|收入)(?:人民币)?[^0-9]{0,8}?([0-9,]+\.\d{2})元?",
)
_EXPENSE_PATTERNS = (
    r"(?:支出|消费|支付|付款|转出|快捷支付|网上支付)(?:人民币)?[^0-9]{0,8}?([0-9,]+\.\d{2})元?",
)
_GENERIC_AMOUNT_PATTERN = r"[¥￥]\s*([0-9,]+\.\d{2})"
_CARD_TAIL_PATTERN = r"尾号\s*(\d{3,4})"
_DATE_PATTERNS = (
    (r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", None),
    (r"(\d{1,2})月(\d{1,2})日", "year_current"),
)


def parse_bank_sms(text: str, source_name: str = "bank_sms", reference: str = "") -> RawTransaction | None:
    """Parse one bank dynamic-account SMS into a RawTransaction.

    Returns ``None`` when no amount/direction signal can be extracted.
    The external id is a stable hash of the full SMS text so re-delivery of the
    same message is deduplicated downstream.
    """
    text = text.strip()
    if not text:
        return None

    amount = None
    direction = None
    for pattern in _INCOME_PATTERNS:
        match = re.search(pattern, text)
        if match:
            amount = _to_decimal(match.group(1))
            direction = BillDirection.INCOME
            break
    if direction is None:
        for pattern in _EXPENSE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                amount = _to_decimal(match.group(1))
                direction = BillDirection.EXPENSE
                break
    if amount is None:
        generic = re.search(_GENERIC_AMOUNT_PATTERN, text)
        if not generic:
            return None
        amount = _to_decimal(generic.group(1))
        direction = BillDirection.INCOME if any(k in text for k in ("收入", "到账", "入账", "存入", "转入")) else BillDirection.EXPENSE

    card_match = re.search(_CARD_TAIL_PATTERN, text)
    card_last4 = card_match.group(1) if card_match else ""

    occurred_on = _parse_date(text)

    merchant = ""
    bracket = re.search(r"《(.+?)》", text)
    if bracket:
        merchant = bracket.group(1)
    else:
        quoted = re.search(r"向(\S{2,30}?)(?:支付|付款|转账|消费)", text)
        if quoted:
            merchant = quoted.group(1)

    external_id = "sms:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    del reference

    return RawTransaction(
        source_name=source_name,
        occurred_on=occurred_on,
        amount=amount,
        direction=direction,
        merchant_name=merchant or "银行卡交易",
        channel="bank_sms",
        card_last4=card_last4,
        note=text[:200],
        external_id=external_id,
        raw_data={"sms_text": text},
    )


def _to_decimal(value: str) -> Decimal | None:
    try:
        value = value.replace(",", "")
        return abs(Decimal(value))
    except InvalidOperation:
        return None


def _parse_date(text: str) -> date:
    from datetime import date as date_cls

    today = date_cls.today()
    for pattern, _mode in _DATE_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue
        groups = [int(g) for g in match.groups()]
        try:
            if len(groups) == 3:  # full year present
                return date_cls(groups[0], groups[1], groups[2])
            # "7月2日" style: assume current year.
            return date_cls(today.year, groups[0], groups[1])
        except ValueError:
            continue
    return today
