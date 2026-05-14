from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .enums import BillDirection, ImportJobStatus, MergeStatus, SubItemStatus, TaskStatus


class TaskSubItemBase(BaseModel):
    title: str
    description: str = ""
    status: SubItemStatus = SubItemStatus.PENDING
    sort_order: int = 0


class TaskSubItemCreate(TaskSubItemBase):
    pass


class TaskSubItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: SubItemStatus | None = None
    sort_order: int | None = None


class TaskSubItemRead(TaskSubItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    def completed(self) -> bool:
        return self.status == SubItemStatus.COMPLETED


class TaskBase(BaseModel):
    title: str
    description: str = ""
    task_date: date | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    status: TaskStatus = TaskStatus.SCHEDULED
    priority: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    is_pinned: bool = False
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_spec_field_names(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        aliases = {
            "scheduled_date": "task_date",
            "start_time": "start_at",
            "due_time": "due_at",
            "notes": "note",
        }
        for public_name, internal_name in aliases.items():
            if public_name in normalized and internal_name not in normalized:
                normalized[internal_name] = normalized[public_name]
        return normalized


class TaskCreate(TaskBase):
    subitems: list[TaskSubItemCreate] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    task_date: date | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None
    is_pinned: bool | None = None
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_spec_field_names(cls, data):
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        aliases = {
            "scheduled_date": "task_date",
            "start_time": "start_at",
            "due_time": "due_at",
            "notes": "note",
        }
        for public_name, internal_name in aliases.items():
            if public_name in normalized and internal_name not in normalized:
                normalized[internal_name] = normalized[public_name]
        return normalized


class TaskStatusChange(BaseModel):
    status: TaskStatus
    reason: str = ""
    source: str = "api"


class TaskStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    old_status: TaskStatus | None
    new_status: TaskStatus
    reason: str
    changed_at: datetime
    source: str


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    subitems: list[TaskSubItemRead] = Field(default_factory=list)
    history: list[TaskStatusHistoryRead] = Field(default_factory=list)

    @computed_field
    def scheduled_date(self) -> date | None:
        return self.task_date

    @computed_field
    def start_time(self) -> datetime | None:
        return self.start_at

    @computed_field
    def due_time(self) -> datetime | None:
        return self.due_at

    @computed_field
    def notes(self) -> str:
        return self.note


class CalendarDaySummary(BaseModel):
    date: date
    total: int
    scheduled: int
    in_progress: int
    on_hold: int
    blocked: int = 0
    incomplete: int = 0
    completed: int
    cancelled: int
    has_pinned: bool = False
    highest_priority: int | None = None
    dominant_status: TaskStatus | None
    status_summary: str = ""


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    filename: str
    status: ImportJobStatus
    raw_count: int
    normalized_count: int
    merged_count: int
    error_message: str
    logs: list[dict]
    created_at: datetime


class NormalizedTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_job_id: int
    raw_transaction_id: int | None
    occurred_on: date
    amount: Decimal
    direction: BillDirection
    merchant_name: str
    normalized_merchant: str
    source_name: str
    channel: str
    external_id: str
    note: str
    card_last4: str
    dedupe_key: str
    merge_status: MergeStatus
    category_suggested: str
    category_final: str
    classification_confidence: float
    classification_reason: str
    classifier_name: str
    created_at: datetime


class MergedTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_on: date
    amount: Decimal
    direction: BillDirection
    merchant_name: str
    normalized_merchant: str
    source_name: str
    category: str
    confidence: float
    reason: str
    duplicate_count: int
    is_active: bool
    created_at: datetime


class MonthlySummary(BaseModel):
    month: str
    total_expense: Decimal
    total_income: Decimal
    by_category: dict[str, Decimal]
    by_source: dict[str, Decimal]
    by_account: dict[str, Decimal]
    duplicates: list[MergedTransactionRead]
    anomalies: list[MergedTransactionRead]


class ReanalyzeRequest(BaseModel):
    import_job_id: int | None = None


class ConnectionConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    api_key: str = "dev-token"
    verify_tls: bool = True
    server_cert_path: str | None = None
    client_cert_path: str | None = None
    client_key_path: str | None = None
    allow_insecure_localhost: bool = False
    timeout_seconds: float = 15.0


class DesktopPreferences(BaseModel):
    opacity: float = Field(default=0.92, ge=0.2, le=1.0)
    theme: str = "light"
    calendar_mode: str = "month"
    always_on_top: bool = False
    compact_mode: bool = False


class ModelCallLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    classifier_name: str
    request_payload: dict
    response_payload: dict
    latency_ms: int
    success: bool
    error_message: str
    created_at: datetime


class EmailAccountCreate(BaseModel):
    name: str
    imap_host: str
    imap_port: int = 993
    username: str
    password: str
    folder: str = "INBOX"
    use_ssl: bool = True
    is_active: bool = True


class EmailAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    imap_host: str
    imap_port: int
    username: str
    folder: str
    use_ssl: bool
    is_active: bool
    last_import_at: datetime | None
    created_at: datetime


class EmailAccountUpdate(BaseModel):
    name: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    username: str | None = None
    password: str | None = None
    folder: str | None = None
    use_ssl: bool | None = None
    is_active: bool | None = None


class EmailImportPreview(BaseModel):
    uid: str
    subject: str
    from_addr: str
    date: str


class EmailImportResult(BaseModel):
    source_name: str
    transaction_count: int
    errors: list[str]


class ClientSettings(BaseModel):
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    desktop: DesktopPreferences = Field(default_factory=DesktopPreferences)
    default_email_account_id: int | None = None
