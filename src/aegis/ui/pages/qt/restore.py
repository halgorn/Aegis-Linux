"""Restore page — backups created by the Cleaner."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services import backup_service as backup_svc
from aegis.ui.widgets.qt import make_title
from aegis.ui.pages.qt._helpers import _show_toast


class RestorePage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._backups: list = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(make_title("Restore",
            "Backups created by the Cleaner. Restore any backup to revert changes."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["ID", "Created", "Reason", "Files"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)
        bar = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._refresh)
        self._btn_restore = QPushButton("Restore selected")
        self._btn_restore.setObjectName("danger")
        self._btn_restore.clicked.connect(self._restore)
        bar.addStretch(); bar.addWidget(self._btn_refresh); bar.addWidget(self._btn_restore)
        bw = QWidget(); bw.setLayout(bar); outer.addWidget(bw)

    def on_show(self) -> None:
        self._refresh()

    def cancel_pending(self) -> None:
        pass

    def _refresh(self) -> None:
        try:
            backups = backup_svc.list_backups()
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Cannot list backups: {e}", "error")
            backups = []
        self._backups = backups
        self._tbl.setRowCount(len(backups))
        for i, b in enumerate(backups):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(b.id)))
            self._tbl.setItem(i, 1, QTableWidgetItem(b.created_at[:19]))
            self._tbl.setItem(i, 2, QTableWidgetItem(b.reason or ""))
            self._tbl.setItem(i, 3, QTableWidgetItem(str(len(b.files))))

    def _restore(self) -> None:
        rows = self._tbl.selectionModel().selectedRows()
        if not rows:
            _show_toast(self, "No backup selected.", "warn"); return
        bid = int(self._tbl.item(rows[0].row(), 0).text())
        confirm = QMessageBox.question(
            self, "Confirm restore",
            f"Restore backup #{bid}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            backup_svc.restore(self._backups[rows[0].row()])
            _show_toast(self, f"Backup #{bid} restored.", "success")
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Restore failed: {e}", "error")