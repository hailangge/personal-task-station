from __future__ import annotations

from decimal import Decimal

import pytest

from personal_task_station.server.importers.sms import parse_bank_sms
from personal_task_station.server.services.ingest import IngestService
from personal_task_station.shared.database import Base, get_engine
from personal_task_station.shared.settings import AppSettings


SMS_EXPENSE = "【招商银行】您尾号1234的账户7月1日12:00完成快捷支付交易人民币100.00元"
SMS_INCOME = "【工商银行】您尾号0001的账户7月2日入账工资12,000.00元"
SMS_MERCHANT = "您尾号8888卡向京东商户支付¥45.60"


@pytest.fixture
def settings(tmp_path):
    return AppSettings.load()


@pytest.fixture
def ingest_service(database_url, settings):
    Base.metadata.create_all(bind=get_engine(database_url))
    session_factory = get_session_factory(database_url)
    session = session_factory()
    try:
        yield IngestService(session, settings=settings)
        session.commit()
    finally:
        session.close()


def get_session_factory(database_url):
    from personal_task_station.shared.database import get_session_factory as _gsf

    return _gsf(database_url)


class TestBankSmsParser:
    def test_expense_template(self):
        tx = parse_bank_sms(SMS_EXPENSE)
        assert tx is not None
        assert tx.amount == Decimal("100.00")
        assert tx.direction.value == "expense"
        assert tx.card_last4 == "1234"
        assert tx.external_id.startswith("sms:")

    def test_income_template(self):
        tx = parse_bank_sms(SMS_INCOME)
        assert tx is not None
        assert tx.amount == Decimal("12000.00")
        assert tx.direction.value == "income"

    def test_yuan_template_merchant(self):
        tx = parse_bank_sms(SMS_MERCHANT)
        assert tx is not None
        assert tx.amount == Decimal("45.60")
        assert tx.direction.value == "expense"
        assert tx.merchant_name == "京东商户"

    def test_marketing_text_ignored(self):
        assert parse_bank_sms("今晚八点全场五折，点击链接立即抢购！") is None
        assert parse_bank_sms("") is None


class TestIngestServiceDelivery:
    def test_deliver_sms_creates_transaction_once(self, ingest_service: IngestService):
        report = ingest_service.deliver_sms_text(SMS_EXPENSE)
        assert report.status == "created"
        assert report.transaction_count == 1
        assert report.import_job_id is not None

        # Same text again -> stable external id -> duplicate skipped.
        second = ingest_service.deliver_sms_text(SMS_EXPENSE)
        assert second.status == "skipped_duplicate"
        assert second.duplicate_count == 1

    def test_different_messages_both_ingested(self, ingest_service: IngestService):
        assert ingest_service.deliver_sms_text(SMS_EXPENSE).status == "created"
        assert ingest_service.deliver_sms_text(SMS_INCOME).status == "created"
        assert ingest_service.deliver_sms_text(SMS_MERCHANT).status == "created"

    def test_non_bill_text_is_reported_ignored(self, ingest_service: IngestService):
        report = ingest_service.deliver_sms_text("无关短信内容")
        assert report.status == "ignored"

    def test_ingested_lands_in_ledger(self, ingest_service: IngestService):
        from personal_task_station.shared.models import NormalizedTransaction

        ingest_service.deliver_sms_text(SMS_EXPENSE)
        rows = ingest_service.session.query(NormalizedTransaction).all()
        assert len(rows) == 1
        assert rows[0].amount == Decimal("100.00")
        assert rows[0].merchant_name == "银行卡交易"
        assert rows[0].card_last4 == "1234"
