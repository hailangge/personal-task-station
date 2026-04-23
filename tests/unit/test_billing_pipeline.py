from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from personal_task_station.server.services.billing import BillingService
from personal_task_station.shared.database import Base, get_engine, session_scope


def test_billing_pipeline_imports_merges_and_summarizes(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    content = Path("fixtures/sample_transactions.csv").read_bytes()
    with session_scope(database_url) as session:
        service = BillingService(session)
        job = service.import_csv_bytes(source_name="mock", filename="sample_transactions.csv", content=content)
        assert job.status.value == "completed"
        assert job.raw_count == 5
        assert len(service.list_duplicates()) == 1

        summary = service.monthly_summary(2026, 3)
        assert summary.total_expense == Decimal("1613.50")
        assert summary.total_income == Decimal("12000.00")
        assert summary.by_category["groceries"] == Decimal("25.50")
        assert summary.by_category["housing"] == Decimal("1500.00")
        assert len(summary.anomalies) == 1


def test_undo_merge_restores_individual_records(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    content = Path("fixtures/sample_transactions.csv").read_bytes()
    with session_scope(database_url) as session:
        service = BillingService(session)
        service.import_csv_bytes(source_name="mock", filename="sample_transactions.csv", content=content)
        merged = service.list_duplicates()[0]
        service.undo_merge(merged.id)
        assert service.list_duplicates() == []
        summary = service.monthly_summary(2026, 3)
        assert summary.total_expense == Decimal("1639.00")
