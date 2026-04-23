from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.shared.schemas import MonthlySummary, NormalizedTransactionRead


class FinanceView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.month_selector = QDateEdit()
        self.month_selector.setDisplayFormat("yyyy-MM")
        self.month_selector.setDate(QDate.currentDate())
        self.month_selector.setCalendarPopup(True)
        self.load_button = QPushButton("Load summary")

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

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Month"))
        controls.addWidget(self.month_selector)
        controls.addWidget(self.load_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(summary_group)
        layout.addWidget(self.category_table)
        layout.addWidget(self.transaction_table)

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
