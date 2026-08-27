from __future__ import annotations

from .alipay import AlipayEmailParser
from .alipay_bill_zip import AlipayBillZipParser
from .bankcomm import BankcommEmailParser
from .cmb import CmbEmailParser
from .generic import GenericNotificationParser
from .invoice_pdf import InvoicePdfEmailParser
from .jd import JdEmailParser
from .pdd import PddEmailParser
from .taobao import TaobaoEmailParser
from .wechat import WechatEmailParser
from .wechat_bill_zip import WechatBillZipParser

# Attachment parsers come first so official bill/invoice emails are handled by
# the structured-file parsers instead of the HTML notification ones.
PARSERS: list[type] = [
    WechatBillZipParser,
    AlipayBillZipParser,
    InvoicePdfEmailParser,
    CmbEmailParser,
    BankcommEmailParser,
    AlipayEmailParser,
    WechatEmailParser,
    JdEmailParser,
    TaobaoEmailParser,
    PddEmailParser,
    GenericNotificationParser,
]

__all__ = [
    "AlipayBillZipParser",
    "AlipayEmailParser",
    "BankcommEmailParser",
    "CmbEmailParser",
    "GenericNotificationParser",
    "InvoicePdfEmailParser",
    "JdEmailParser",
    "PARSERS",
    "PddEmailParser",
    "TaobaoEmailParser",
    "WechatBillZipParser",
    "WechatEmailParser",
]

