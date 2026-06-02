from __future__ import annotations

from .alipay import AlipayEmailParser
from .bankcomm import BankcommEmailParser
from .cmb import CmbEmailParser
from .generic import GenericNotificationParser
from .jd import JdEmailParser
from .pdd import PddEmailParser
from .taobao import TaobaoEmailParser
from .wechat import WechatEmailParser

__all__ = [
    "AlipayEmailParser",
    "BankcommEmailParser",
    "CmbEmailParser",
    "GenericNotificationParser",
    "JdEmailParser",
    "PddEmailParser",
    "TaobaoEmailParser",
    "WechatEmailParser",
]
