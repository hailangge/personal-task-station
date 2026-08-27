"""Vision-model extraction of payment screenshots via LiteLLM.

Reuses the existing ``PTS_LITELLM_*`` configuration (see
:class:`~personal_task_station.shared.settings.AppSettings`). The extractor is
confirm-first by design: callers persist proposals as drafts that a human must
approve before anything reaches the ledger.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from personal_task_station.shared.enums import BillDirection
from personal_task_station.shared.settings import AppSettings


class VisionExtractionError(RuntimeError):
    """Raised when the screenshot cannot be converted into a proposal."""


_SYSTEM_PROMPT = (
    "You extract structured payment data from Chinese payment app screenshots "
    "(Alipay, WeChat Pay, bank apps, e-commerce order pages). "
    "Respond with JSON only."
)

_USER_PROMPT = """从这张支付/账单截图中提取交易信息。只输出 JSON，格式如下：
{
  "occurred_on": "YYYY-MM-DD",
  "amount": "金额数字字符串（正数）",
  "direction": "expense 或 income",
  "merchant_name": "商户或交易对方名称",
  "note": "商品说明或备注（可空字符串）"
}
若某个字段在截图中无法确定，amount/occurred_on 取 null；merchant_name 缺失时用空字符串。"""


def extract_transaction_from_image(
    image_bytes: bytes,
    mime_type: str = "image/png",
    settings: AppSettings | None = None,
) -> dict:
    """Return a normalized proposal dict extracted from one screenshot."""
    settings = settings or AppSettings.load()
    if not settings.litellm_model:
        raise VisionExtractionError(
            "Vision model is not configured. Set PTS_LITELLM_MODEL (and "
            "PTS_LITELLM_BASE_URL / PTS_LITELLM_API_KEY) to enable screenshot extraction."
        )
    try:
        from litellm import completion  # type: ignore[import-not-found]
    except ImportError as exc:
        raise VisionExtractionError(
            "LiteLLM is not installed. Run pip install 'personal-task-station[litellm]'."
        ) from exc

    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"

    response = completion(
        model=settings.litellm_model,
        api_key=settings.litellm_api_key,
        api_base=settings.litellm_base_url,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        timeout=settings.request_timeout_seconds,
    )
    content = response.choices[0].message.content or ""
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise VisionExtractionError("Vision model did not return JSON payload.")
    try:
        raw_payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VisionExtractionError("Vision model returned malformed JSON.") from exc

    occurred_raw = str(raw_payload.get("occurred_on") or "").strip()
    amount_raw = str(raw_payload.get("amount") or "").strip()
    if not occurred_raw or not amount_raw:
        raise VisionExtractionError(
            "Screenshot is missing amount or date fields; manual input required."
        )
    try:
        occurred_on = date.fromisoformat(occurred_raw.replace("/", "-")[:10])
    except ValueError as exc:
        raise VisionExtractionError(f"Invalid date in vision output: {occurred_raw!r}") from exc
    try:
        amount = abs(Decimal(amount_raw.replace(",", "")))
    except InvalidOperation as exc:
        raise VisionExtractionError(f"Invalid amount in vision output: {amount_raw!r}") from exc

    direction_raw = str(raw_payload.get("direction") or "expense").strip().lower()
    direction = BillDirection.INCOME if direction_raw.startswith("in") else BillDirection.EXPENSE

    return {
        "occurred_on": occurred_on.isoformat(),
        "amount": str(amount),
        "direction": direction.value if hasattr(direction, "value") else str(direction),
        "merchant_name": str(raw_payload.get("merchant_name") or "").strip(),
        "note": str(raw_payload.get("note") or "").strip(),
    }
