from __future__ import annotations

from pathlib import Path


def test_billing_import_summary_and_undo(client, auth_headers):
    with Path("fixtures/sample_transactions.csv").open("rb") as handle:
        response = client.post(
            "/billing/import",
            headers=auth_headers,
            data={"source_name": "fixture"},
            files={"file": ("sample_transactions.csv", handle, "text/csv")},
        )
    assert response.status_code == 201, response.text

    response = client.get("/billing/summary/monthly", headers=auth_headers, params={"year": 2026, "month": 3})
    assert response.status_code == 200
    summary = response.json()
    assert summary["total_expense"] == "1613.50"
    assert summary["total_income"] == "12000.00"
    assert len(summary["duplicates"]) == 1

    merged_id = summary["duplicates"][0]["id"]
    response = client.post(f"/billing/merged/{merged_id}/undo", headers=auth_headers)
    assert response.status_code == 200

    response = client.get("/billing/duplicates", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []
