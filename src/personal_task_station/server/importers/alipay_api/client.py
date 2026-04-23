from __future__ import annotations

import base64
import json
import urllib.parse
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.shared.enums import BillDirection


@dataclass
class AlipayConfig:
    app_id: str
    private_key_path: str
    alipay_public_key_path: str
    # bill_type: trade = 交易账单, signcustomer = 资金账单
    bill_type: str = "trade"


class AlipayBillClient:
    """Client for Alipay bill download API.

    Uses RSA2 signature as required by Alipay Open Platform.
    Official docs: https://opendocs.alipay.com/open/02np98
    """

    GATEWAY = "https://openapi.alipay.com/gateway.do"
    BILL_API = "alipay.data.dataservice.bill.downloadurl.query"

    def __init__(self, config: AlipayConfig):
        self.config = config
        self._private_key = None

    def _load_private_key(self):
        if self._private_key is None:
            pem = Path(self.config.private_key_path).read_bytes()
            self._private_key = serialization.load_pem_private_key(pem, password=None)
        return self._private_key

    def _sign(self, params: dict[str, str]) -> str:
        """Generate RSA2 signature for Alipay request."""
        # Sort params by key and join as query string
        filtered = {k: v for k, v in params.items() if k != "sign" and v is not None and v != ""}
        query = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))
        signature = self._load_private_key().sign(
            query.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _build_params(self, bill_date: date) -> dict[str, str]:
        params = {
            "app_id": self.config.app_id,
            "method": self.BILL_API,
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": (date.today()).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps({
                "bill_type": self.config.bill_type,
                "bill_date": bill_date.strftime("%Y-%m-%d"),
            }, separators=(",", ":")),
        }
        params["sign"] = self._sign(params)
        return params

    def download_bill(self, bill_date: date) -> ImportResult:
        """Download bill for a specific date and return parsed transactions.

        Returns empty result if bill not yet generated (T+1 for trade bills).
        """
        result = ImportResult(source_name="alipay_api")
        params = self._build_params(bill_date)

        try:
            response = httpx.post(self.GATEWAY, data=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            result.errors.append(f"API request failed: {exc}")
            return result

        # Check for API-level errors
        alipay_response = data.get(f"{self.BILL_API}_response", {})
        code = alipay_response.get("code", "")
        if code != "10000":
            msg = alipay_response.get("msg", "Unknown error")
            sub_msg = alipay_response.get("sub_msg", "")
            result.errors.append(f"Alipay API error: {msg} - {sub_msg}")
            return result

        bill_download_url = alipay_response.get("bill_download_url", "")
        if not bill_download_url:
            result.errors.append("No bill download URL in response")
            return result

        # Download the bill file (ZIP containing CSV)
        try:
            bill_response = httpx.get(bill_download_url, timeout=60.0)
            bill_response.raise_for_status()
        except Exception as exc:
            result.errors.append(f"Bill download failed: {exc}")
            return result

        # Parse ZIP -> CSV -> transactions
        return self._parse_bill_content(bill_response.content)

    def _parse_bill_content(self, content: bytes) -> ImportResult:
        """Parse Alipay bill ZIP content."""
        result = ImportResult(source_name="alipay_api")

        try:
            import io

            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Alipay bills typically contain a single CSV file
                csv_name = [name for name in zf.namelist() if name.endswith(".csv")][0]
                csv_content = zf.read(csv_name)
        except Exception as exc:
            result.errors.append(f"ZIP parsing failed: {exc}")
            return result

        # Parse Alipay CSV format
        # Header row starts with # 支付宝业务明细查询
        # Summary rows start with #
        # Data rows are standard CSV
        text = csv_content.decode("utf-8-sig")
        lines = text.splitlines()

        # Find the actual CSV header (first line without leading #)
        data_lines = []
        for line in lines:
            if line.startswith("#"):
                continue
            data_lines.append(line)

        if len(data_lines) < 2:
            result.errors.append("No data rows found in bill CSV")
            return result

        import csv

        reader = csv.DictReader(data_lines)
        for row in reader:
            try:
                tx = self._csv_row_to_transaction(row)
                if tx:
                    result.raw_transactions.append(tx)
            except Exception as exc:
                result.errors.append(f"Row parse error: {exc}")
                result.skipped_count += 1

        return result

    def _csv_row_to_transaction(self, row: dict[str, str]) -> RawTransaction | None:
        """Convert Alipay CSV row to RawTransaction.

        Alipay bill CSV columns (typical):
        支付宝交易号,商户订单号,交易创建时间,付款时间,最近修改时间,
        交易来源地,类型,交易对方,商品名称,金额（元）,收/支,交易状态,
        服务费（元）,成功退款（元）,备注,资金状态
        """
        # Find amount column
        amount_keys = [k for k in row.keys() if "金额" in k and "服务费" not in k and "退款" not in k]
        if not amount_keys:
            return None
        amount_str = row[amount_keys[0]].strip().replace(",", "")
        if not amount_str:
            return None
        amount = Decimal(amount_str)

        # Determine direction
        direction_str = ""
        for k in row.keys():
            if "收/支" in k or "direction" in k.lower():
                direction_str = row[k].strip()
                break

        direction = BillDirection.EXPENSE
        if direction_str == "收入":
            direction = BillDirection.INCOME
        elif direction_str == "支出":
            direction = BillDirection.EXPENSE
        elif amount < 0:
            direction = BillDirection.INCOME
            amount = -amount

        # Parse date
        occurred_on = date.today()
        for k in row.keys():
            if "创建时间" in k or "付款时间" in k:
                date_str = row[k].strip().split()[0]
                try:
                    occurred_on = date.fromisoformat(date_str.replace("/", "-"))
                except ValueError:
                    pass
                break

        # Merchant name
        merchant = ""
        for k in row.keys():
            if "交易对方" in k:
                merchant = row[k].strip()
                break
        if not merchant:
            for k in row.keys():
                if "商品名称" in k:
                    merchant = row[k].strip()
                    break

        # External ID (Alipay trade no)
        external_id = ""
        for k in row.keys():
            if "支付宝交易号" in k or "trade_no" in k.lower():
                external_id = row[k].strip()
                break

        # Note
        note = ""
        for k in row.keys():
            if "备注" in k or "note" in k.lower():
                note = row[k].strip()
                break

        return RawTransaction(
            source_name="alipay_api",
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant or "支付宝交易",
            channel="alipay",
            external_id=external_id,
            note=note,
            raw_data=dict(row),
        )

    def download_range(self, start_date: date, end_date: date) -> list[ImportResult]:
        """Download bills for a date range (inclusive)."""
        results = []
        current = start_date
        while current <= end_date:
            result = self.download_bill(current)
            results.append(result)
            current += timedelta(days=1)
        return results
