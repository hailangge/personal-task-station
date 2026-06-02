from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.shared.schemas import MergedTransactionRead, MonthlySummary, NormalizedTransactionRead


class FinanceView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.month_selector = QDateEdit()
        self.month_selector.setDisplayFormat("yyyy-MM")
        self.month_selector.setDate(QDate.currentDate())
        self.month_selector.setCalendarPopup(True)
        self.load_button = QPushButton("Load summary")
        self.source_input = QLineEdit("csv")
        self.source_input.setPlaceholderText("Source name")
        self.import_button = QPushButton("Import CSV")
        self.reanalyze_button = QPushButton("Reanalyze")
        self.undo_duplicate_button = QPushButton("Undo selected duplicate")
        self.status_label = QLabel("Import CSV files manually; email/bank automation is optional and not required.")
        self.status_label.setWordWrap(True)

        summary_group = QGroupBox("Monthly summary")
        summary_form = QFormLayout(summary_group)
        self.expense_label = QLabel("0.00")
        self.income_label = QLabel("0.00")
        summary_form.addRow("Expense", self.expense_label)
        summary_form.addRow("Income", self.income_label)

        self.category_table = QTableWidget(0, 2)
        self.category_table.setHorizontalHeaderLabels(["Category", "Amount"])
        self.transaction_table = QTableWidget(0, 4)
        self.transaction_table.setHorizontalHeaderLabels(["Date", "Merchant", "Category", "Amount"])
        self.duplicates_table = QTableWidget(0, 6)
        self.duplicates_table.setHorizontalHeaderLabels(["ID", "Date", "Merchant", "Category", "Amount", "Count"])

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Month"))
        controls.addWidget(self.month_selector)
        controls.addWidget(self.load_button)
        controls.addWidget(QLabel("Source"))
        controls.addWidget(self.source_input)
        controls.addWidget(self.import_button)
        controls.addWidget(self.reanalyze_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status_label)
        layout.addWidget(summary_group)
        layout.addWidget(self.category_table)
        layout.addWidget(QLabel("Transactions"))
        layout.addWidget(self.transaction_table)
        duplicate_controls = QHBoxLayout()
        duplicate_controls.addWidget(QLabel("Detected duplicates"))
        duplicate_controls.addWidget(self.undo_duplicate_button)
        duplicate_controls.addStretch(1)
        layout.addLayout(duplicate_controls)
        layout.addWidget(self.duplicates_table)

    def set_summary(self, summary: MonthlySummary) -> None:
        self.expense_label.setText(str(summary.total_expense))
        self.income_label.setText(str(summary.total_income))
        self.category_table.setRowCount(len(summary.by_category))
        for row, (category, amount) in enumerate(summary.by_category.items()):
            self.category_table.setItem(row, 0, QTableWidgetItem(category))
            self.category_table.setItem(row, 1, QTableWidgetItem(str(amount)))

    def set_transactions(self, transactions: list[NormalizedTransactionRead]) -> None:
        self.transaction_table.setRowCount(len(transactions))
        for row, transaction in enumerate(transactions):
            self.transaction_table.setItem(row, 0, QTableWidgetItem(transaction.occurred_on.isoformat()))
            self.transaction_table.setItem(row, 1, QTableWidgetItem(transaction.merchant_name))
            self.transaction_table.setItem(row, 2, QTableWidgetItem(transaction.category_final))
            self.transaction_table.setItem(row, 3, QTableWidgetItem(str(Decimal(str(transaction.amount)))))

    def set_duplicates(self, duplicates: list[MergedTransactionRead]) -> None:
        self.duplicates_table.setRowCount(len(duplicates))
        for row, duplicate in enumerate(duplicates):
            self.duplicates_table.setItem(row, 0, QTableWidgetItem(str(duplicate.id)))
            self.duplicates_table.setItem(row, 1, QTableWidgetItem(duplicate.occurred_on.isoformat()))
            self.duplicates_table.setItem(row, 2, QTableWidgetItem(duplicate.merchant_name))
            self.duplicates_table.setItem(row, 3, QTableWidgetItem(duplicate.category))
            self.duplicates_table.setItem(row, 4, QTableWidgetItem(str(Decimal(str(duplicate.amount)))))
            self.duplicates_table.setItem(row, 5, QTableWidgetItem(str(duplicate.duplicate_count)))

    def selected_duplicate_id(self) -> int | None:
        selected = self.duplicates_table.selectedItems()
        if not selected:
            return None
        item = self.duplicates_table.item(selected[0].row(), 0)
        return int(item.text()) if item else None
