from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import BillDirection, ImportJobStatus, MergeStatus, SubItemStatus, TaskStatus


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    task_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, omit_aliases=False), default=TaskStatus.SCHEDULED)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")

    subitems: Mapped[list["TaskSubItem"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskSubItem.sort_order",
    )
    history: Mapped[list["TaskStatusHistory"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskStatusHistory.changed_at",
    )


class TaskSubItem(TimestampMixin, Base):
    __tablename__ = "task_subitems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[SubItemStatus] = mapped_column(Enum(SubItemStatus), default=SubItemStatus.PENDING)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    task: Mapped["Task"] = relationship(back_populates="subitems")


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    old_status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus, omit_aliases=False), nullable=True)
    new_status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, omit_aliases=False))
    reason: Mapped[str] = mapped_column(Text, default="")
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(50), default="system")

    task: Mapped["Task"] = relationship(back_populates="history")


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class BillImportJob(Base):
    __tablename__ = "bill_import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[ImportJobStatus] = mapped_column(Enum(ImportJobStatus), default=ImportJobStatus.PENDING)
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    logs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    raw_transactions: Mapped[list["RawTransaction"]] = relationship(
        back_populates="import_job",
        cascade="all, delete-orphan",
        order_by="RawTransaction.row_number",
    )
    normalized_transactions: Mapped[list["NormalizedTransaction"]] = relationship(
        back_populates="import_job",
        cascade="all, delete-orphan",
        order_by="NormalizedTransaction.id",
    )


class RawTransaction(Base):
    __tablename__ = "raw_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("bill_import_jobs.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    source_name: Mapped[str] = mapped_column(String(120))
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    original_reference: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    import_job: Mapped["BillImportJob"] = relationship(back_populates="raw_transactions")
    normalized_transaction: Mapped["NormalizedTransaction | None"] = relationship(
        back_populates="raw_transaction",
        uselist=False,
    )


class NormalizedTransaction(Base):
    __tablename__ = "normalized_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("bill_import_jobs.id", ondelete="CASCADE"))
    raw_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    occurred_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[BillDirection] = mapped_column(Enum(BillDirection))
    merchant_name: Mapped[str] = mapped_column(String(200))
    normalized_merchant: Mapped[str] = mapped_column(String(200))
    source_name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(120), default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    card_last4: Mapped[str] = mapped_column(String(8), default="")
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    merge_status: Mapped[MergeStatus] = mapped_column(Enum(MergeStatus), default=MergeStatus.UNMERGED)
    category_suggested: Mapped[str] = mapped_column(String(120), default="")
    category_final: Mapped[str] = mapped_column(String(120), default="")
    classification_confidence: Mapped[float] = mapped_column(default=0.0)
    classification_reason: Mapped[str] = mapped_column(Text, default="")
    classifier_name: Mapped[str] = mapped_column(String(80), default="fallback_rules")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    import_job: Mapped["BillImportJob"] = relationship(back_populates="normalized_transactions")
    raw_transaction: Mapped["RawTransaction | None"] = relationship(back_populates="normalized_transaction")
    merged_memberships: Mapped[list["MergedTransactionMember"]] = relationship(
        back_populates="normalized_transaction",
        cascade="all, delete-orphan",
    )


class MergedTransaction(Base):
    __tablename__ = "merged_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[BillDirection] = mapped_column(Enum(BillDirection))
    merchant_name: Mapped[str] = mapped_column(String(200))
    normalized_merchant: Mapped[str] = mapped_column(String(200))
    source_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[float] = mapped_column(default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    members: Mapped[list["MergedTransactionMember"]] = relationship(
        back_populates="merged_transaction",
        cascade="all, delete-orphan",
    )


class MergedTransactionMember(Base):
    __tablename__ = "merged_transaction_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merged_transaction_id: Mapped[int] = mapped_column(ForeignKey("merged_transactions.id", ondelete="CASCADE"))
    normalized_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("normalized_transactions.id", ondelete="CASCADE")
    )

    merged_transaction: Mapped["MergedTransaction"] = relationship(back_populates="members")
    normalized_transaction: Mapped["NormalizedTransaction"] = relationship(back_populates="merged_memberships")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ModelCallLog(Base):
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    classifier_name: Mapped[str] = mapped_column(String(80))
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    imap_host: Mapped[str] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    username: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String(255))  # In production, encrypt this
    folder: Mapped[str] = mapped_column(String(120), default="INBOX")
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_import_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailImportLog(Base):
    __tablename__ = "email_import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email_account_id: Mapped[int] = mapped_column(ForeignKey("email_accounts.id", ondelete="CASCADE"))
    email_uid: Mapped[str] = mapped_column(String(120))
    email_subject: Mapped[str] = mapped_column(String(500), default="")
    email_from: Mapped[str] = mapped_column(String(255), default="")
    parser_used: Mapped[str] = mapped_column(String(120), default="")
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
