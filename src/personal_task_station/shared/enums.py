from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SubItemStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BillDirection(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class ImportJobStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class MergeStatus(str, Enum):
    UNMERGED = "unmerged"
    MERGED = "merged"
    UNDONE = "undone"

