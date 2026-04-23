from __future__ import annotations

from .cmb import CmbEmailParser
from .alipay import AlipayEmailParser
from .jd import JdEmailParser
from .taobao import TaobaoEmailParser
from .wechat import WechatEmailParser
from .pdd import PddEmailParser
from .generic import GenericNotificationParser

__all__ = [
    "CmbEmailParser",
    "AlipayEmailParser",
    "JdEmailParser",
    "TaobaoEmailParser",
    "WechatEmailParser",
    "PddEmailParser",
    "GenericNotificationParser",
]
