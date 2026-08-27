"""End-to-end test of the bill-mailbox sync pipeline with a fake IMAP backend.

The user will inject real test emails later; this test pins the exact path the
server takes when those emails arrive: IMAP fetch -> bill-only gate ->
attachment parser -> billing pipeline -> /billing/transactions.
"""

from __future__ import annotations

import io
import zipfile
from personal_task_station.server.importers.email.client import FetchedEmail


def _wechat_bill_zip() -> bytes:
    csv_text = "\n".join(
        [
            "微信支付账单明细",
            "----------------------------------------",
            "微信昵称：[tester]",
            "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注",
            "2026-08-01 12:00:00,商户消费,全家便利店,早餐,支出,25.50,零钱,支付成功,E2E20260801A,,",
            "2026-08-02 09:30:00,商户消费,美团平台商户,午餐,支出,42.80,工商银行卡(1234),支付成功,E2E20260802B,,",
        ]
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("微信支付交易明细证明(20260801-20260831).csv", csv_text)
    return buf.getvalue()


def _install_fake_mailbox(monkeypatch, emails: list[FetchedEmail]):
    """Replace EmailImportService's IMAP client with a canned mailbox."""
    from personal_task_station.server.importers.email import service as email_service_module

    class FakeEmailClient(object):
        def __init__(self, config):
            self.config = config

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def fetch_unseen_since(self, since_date=None, ignore_seen=False, sender_filter=None):
            return list(emails)

        def mark_seen(self, uid):
            return None

    monkeypatch.setattr(email_service_module, "EmailClient", FakeEmailClient)


def test_sync_pipeline_ingests_wechat_zip_email(app, client, auth_headers, database_url, monkeypatch):
    emails = [
        FetchedEmail(
            uid="101",
            subject="微信支付账单明细",
            from_addr="service@tenpay.com",
            date="Tue, 1 Aug 2026 10:00:00 +0800",
            body_html="",
            body_text="",
            attachments=[("bills.zip", _wechat_bill_zip())],
        ),
        FetchedEmail(
            uid="102",
            subject="周末限时大促销，全场五折！",
            from_addr="marketing@jd.com",
            date="Tue, 1 Aug 2026 11:00:00 +0800",
            body_html="<p>优惠券</p>",
            body_text="",
            attachments=[],
        ),
    ]
    _install_fake_mailbox(monkeypatch, emails)

    created = client.post(
        "/email-import/accounts",
        json={
            "name": "billbox",
            "imap_host": "imap.example.test",
            "imap_port": 993,
            "username": "2924799749@example.test",
            "password": "auth-code",
            "folder": "INBOX",
            "use_ssl": True,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]

    jobs = client.post("/email-import/sync?force=true", headers=auth_headers)
    assert jobs.status_code == 200, jobs.text
    returned = jobs.json()
    assert len(returned) == 1
    assert returned[0]["source_name"] == "email:billbox"
    assert returned[0]["normalized_count"] == 2

    logs = client.get(f"/email-import/accounts/{account_id}/logs", headers=auth_headers)
    assert logs.status_code == 200
    assert len(logs.json()) >= 1

    transactions = client.get("/billing/transactions", headers=auth_headers)
    assert transactions.status_code == 200
    rows = transactions.json()
    merchants = {row["merchant_name"] for row in rows}
    assert merchants == {"全家便利店", "美团平台商户"}
    external_ids = {row["external_id"] for row in rows}
    assert {"E2E20260801A", "E2E20260802B"} <= external_ids

    # Re-running sync must not double count (mark_seen simulated + no duplicates).
    jobs_again = client.post("/email-import/sync?force=true", headers=auth_headers)
    assert jobs_again.status_code == 200
    # The fake mailbox always returns the same mail, but repeated UID is a new
    # parse of identical rows; the ledger should still hold exactly 2 rows.
    rows_after = client.get("/billing/transactions", headers=auth_headers).json()
    assert len(rows_after) == 2
