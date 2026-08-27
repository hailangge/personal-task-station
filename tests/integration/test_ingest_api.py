from __future__ import annotations

from pathlib import Path


def test_webhook_accepts_json_and_is_idempotent(client, auth_headers):
    text = "【招商银行】您尾号1234的账户7月1日12:00完成快捷支付交易人民币100.00元"
    response = client.post(
        "/ingest/webhook",
        json={"text": text, "source_name": "cmb_sms"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["transaction_count"] == 1
    assert body["import_job_id"] is not None

    repeat = client.post("/ingest/webhook", json={"text": text}, headers=auth_headers)
    assert repeat.status_code == 200
    assert repeat.json()["status"] == "skipped_duplicate"


def test_webhook_plain_text_and_ignored_body(client, auth_headers):
    ok = client.post(
        "/ingest/webhook",
        content="您尾号0001的账户7月2日入账工资12,000.00元".encode("utf-8"),
        headers={**auth_headers, "Content-Type": "text/plain"},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "created"

    ignored = client.post(
        "/ingest/webhook",
        content="纯属营销短信".encode("utf-8"),
        headers={**auth_headers, "Content-Type": "text/plain"},
    )
    assert ignored.json()["status"] == "ignored"

    empty = client.post("/ingest/webhook", json={}, headers=auth_headers)
    assert empty.json()["status"] == "ignored"


def test_webhook_requires_api_key(client):
    unauthenticated = client.post("/ingest/webhook", json={"text": "x"})
    assert unauthenticated.status_code in (401, 403)


def test_screenshot_upload_falls_back_to_manual_confirm(tmp_path, client, auth_headers, monkeypatch):
    monkeypatch.setenv("PTS_DATA_DIR", str(tmp_path / "data"))
    # No PTS_LITELLM_MODEL configured -> draft created without proposal.
    payload = Path("fixtures/sample_invoice.pdf").read_bytes()
    upload = client.post(
        "/ingest/screenshots",
        files={"file": ("shot.png", payload, "image/png")},
        headers=auth_headers,
    )
    assert upload.status_code == 201, upload.text
    draft = upload.json()
    assert draft["status"] == "proposed"
    assert any("not configured" in err for err in draft["extraction_errors"])

    listing = client.get("/ingest/screenshots?status_filter=proposed", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    confirm = client.post(
        f"/ingest/screenshots/{draft['id']}/confirm",
        json={
            "occurred_on": "2026-08-01",
            "amount": "66.50",
            "merchant_name": "手动确认商户",
            "note": "来自截图",
        },
        headers=auth_headers,
    )
    assert confirm.status_code == 200, confirm.text
    confirmed = confirm.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["confirmed_transaction_id"] is not None

    transactions = client.get(
        "/billing/transactions?month=2026-08",
        headers=auth_headers,
    )
    assert transactions.status_code == 200
    entries = [t for t in transactions.json() if t["source_name"] == "screenshot"]
    assert len(entries) == 1
    assert entries[0]["merchant_name"] == "手动确认商户"

    # Confirming again is rejected; re-uploading same image is deduplicated.
    again = client.post(
        f"/ingest/screenshots/{draft['id']}/confirm",
        json={"occurred_on": "2026-08-01", "amount": "1.00"},
        headers=auth_headers,
    )
    assert again.status_code == 400

    duplicate_upload = client.post(
        "/ingest/screenshots",
        files={"file": ("shot.png", payload, "image/png")},
        headers=auth_headers,
    )
    assert duplicate_upload.json()["id"] == draft["id"]


def test_screenshot_discard(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_DATA_DIR", str(tmp_path / "data"))
    upload = client.post(
        "/ingest/screenshots",
        files={"file": ("discard.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
        headers=auth_headers,
    )
    draft_id = upload.json()["id"]
    deleted = client.delete(f"/ingest/screenshots/{draft_id}", headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "discarded"
