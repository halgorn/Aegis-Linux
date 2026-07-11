"""Cleaner page — select + scan + clean targets."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from aegis.core.concurrency import TaskSpec
from aegis.domain.cleaner import CleanKind
from aegis.services.cleaner_service import CleanerService
from aegis.ui.theme import fmt_bytes
from aegis.ui.widgets.qt import ScanButton, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _log, _runner, _set_status, _show_toast, _wire_bridge,
)


class CleanerPage(QWidget):
    """CleanerPage mixes in CancellableScanMixin via direct attribute
    setup — we don't actually call its methods from elsewhere, so we
    keep the dependencies minimal here."""

    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._targets: list = []
        self._checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._render_placeholder()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title(
            "Cleaner",
            "Select what to clean. Dry-run is on by default - no files are removed until you confirm.",
        ))
        bar = QHBoxLayout()
        self._btn_all = QPushButton("Select all")
        self._btn_all.clicked.connect(self._select_all)
        self._btn_none = QPushButton("Select none")
        self._btn_none.clicked.connect(self._select_none)
        self._dryrun = QCheckBox("Dry run")
        self._dryrun.setChecked(True)
        self._btn_scan = ScanButton("Scan", page=self)
        self._btn_scan.clicked.connect(self._refresh)
        self._btn_clean = QPushButton("Clean selected")
        self._btn_clean.setObjectName("danger")
        self._btn_clean.clicked.connect(self._clean)
        bar.addWidget(self._btn_all)
        bar.addWidget(self._btn_none)
        bar.addSpacing(20)
        bar.addWidget(QLabel("Total reclaimable:"))
        self._total_lbl = QLabel("-")
        self._total_lbl.setStyleSheet("font-weight: 600;")
        bar.addWidget(self._total_lbl)
        bar.addStretch()
        bar.addWidget(self._dryrun)
        bar.addWidget(self._btn_scan)
        bar.addWidget(self._btn_clean)
        bw = QWidget(); bw.setLayout(bar)
        outer.addWidget(bw)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "Target", "Description", "Estimated size"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        split.addWidget(self._table)

        detail = QFrame(); detail.setObjectName("card")
        dl = QVBoxLayout(detail); dl.setContentsMargins(16, 14, 16, 14); dl.setSpacing(6)
        dl.addWidget(QLabel("Selection details"))
        self._detail = QTextEdit(); self._detail.setReadOnly(True)
        dl.addWidget(self._detail, 1)
        split.addWidget(detail)
        split.setSizes([820, 380])
        outer.addWidget(split, 1)
        self._table.itemSelectionChanged.connect(self._on_select)

    def on_show(self) -> None:
        self._refresh()

    def _select_all(self) -> None:
        for cb in self._checks.values():
            cb.setChecked(True)

    def _select_none(self) -> None:
        for cb in self._checks.values():
            cb.setChecked(False)

    def _track(self, spec):
        self._pending.append(spec)

    def _untrack(self, spec):
        try:
            self._pending.remove(spec)
        except ValueError:
            pass

    def cancel_pending(self) -> None:
        for spec in list(self._pending):
            spec.cancel()
        self._pending.clear()

    def _refresh(self) -> None:
        _set_status(self, "Scanning cleanable targets...")
        page = self

        def worker():
            _log.info("[cleaner] worker start, %d targets", len(page._targets))
            try:
                from aegis.services.cleaner_service import _estimate_target_size
                for i, t in enumerate(page._targets):
                    current = page._btn_scan._current
                    if current is None or current.cancelled:
                        _log.info("[cleaner] cancelled at i=%d", i)
                        return
                    if t.kind == CleanKind.EXEC:
                        size = 0
                    else:
                        size = _estimate_target_size(t) or 0
                    page._bridge.post(page._update_target_size, t, size)
                    if i % 4 == 0:
                        page._bridge.post(page._update_total)
                page._bridge.post(page._update_total)
                _log.info("[cleaner] worker done")
            except Exception as e:  # noqa: BLE001
                _log.exception("[cleaner] worker failed: %s", e)
                raise

        def on_done(_):
            _log.info("[cleaner] on_done")

        def on_error(exc):
            _log.warning("[cleaner] on_error: %r", exc)
            page._bridge.post(lambda e=exc: _show_toast(page, f"Scan failed: {e}", "error"))

        self._btn_scan.start(self._runner, fn=worker,
                             bridge=self._bridge,
                             name="cleaner-scan",
                             on_done=on_done, on_error=on_error)

    def _render_placeholder(self) -> None:
        from aegis.rules.cleaner_rules import all_targets as _all
        self._targets = list(_all())
        self._checks.clear()
        self._table.setRowCount(len(self._targets))
        for row, t in enumerate(self._targets):
            cb = QCheckBox()
            self._checks[t.id] = cb
            cw = QWidget(); cl = QHBoxLayout(cw); cl.setContentsMargins(8, 0, 8, 0)
            cl.addWidget(cb); cl.addStretch()
            self._table.setCellWidget(row, 0, cw)
            self._table.setItem(row, 1, QTableWidgetItem(t.label))
            self._table.setItem(row, 2, QTableWidgetItem(t.description))
            self._table.setItem(row, 3, QTableWidgetItem("…"))
        self._total_lbl.setText("…")
        self._table.setEnabled(True)
        _set_status(self, f"{len(self._targets)} targets loaded. Click Scan to size.")

    def _update_target_size(self, t, size: int) -> None:
        object.__setattr__(t, "estimated_size", size)
        for row, target in enumerate(self._targets):
            if target is t:
                item = self._table.item(row, 3)
                item.setText(fmt_bytes(size))
                break
        self._update_total()

    def _update_total(self) -> None:
        total = sum(getattr(t, "estimated_size", 0) for t in self._targets)
        self._total_lbl.setText(fmt_bytes(total))
        if all(getattr(t, "estimated_size", 0) > 0 or t.kind.value == "exec"
               for t in self._targets):
            _set_status(self, f"Scan complete. {len(self._targets)} targets, "
                          f"{fmt_bytes(total)} reclaimable.")
            self._btn_scan.finish()

    def _render(self, _targets) -> None:
        if not self._targets:
            self._render_placeholder()

    def _on_select(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._detail.clear(); return
        idx = rows[0].row()
        t = self._targets[idx]
        self._detail.setPlainText(
            f"<b>{t.label}</b><br><br>"
            f"<i>{t.description}</i><br><br>"
            f"<b>Category:</b> {t.category}<br>"
            f"<b>Kind:</b> {t.kind}<br>"
            f"<b>Needs root:</b> {t.needs_root}<br>"
            f"<b>Reversible:</b> {t.reversible}<br>"
            f"<b>Estimated:</b> {fmt_bytes(t.estimated_size)}<br>"
            f"<b>Path count:</b> {len(t.paths)}<br>"
            f"<br><b>Paths:</b><br>"
            + "<br>".join(f"  • {p}" for p in t.paths[:30])
            + (f"<br>  … +{len(t.paths) - 30} more" if len(t.paths) > 30 else "")
        )

    def _clean(self) -> None:
        ids = [tid for tid, cb in self._checks.items() if cb.isChecked()]
        if not ids:
            _show_toast(self, "No targets selected.", "warn"); return
        if not self._dryrun.isChecked():
            from PyQt6.QtWidgets import QMessageBox
            r = QMessageBox.question(
                self, "Confirm cleanup",
                f"Delete files from {len(ids)} targets?\n"
                "This action is reversible only via the Restore page if a backup was made.",
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        if hasattr(self, "_btn_clean_busy") and self._btn_clean_busy:
            return
        self._btn_clean_busy = True
        self._btn_clean.setEnabled(False)
        self._btn_clean.setText("Cleaning…")
        _set_status(self, "Cleaning...")
        dry = self._dryrun.isChecked()

        def run():
            try:
                res = CleanerService().run(target_ids=ids, dry_run=dry, create_backup=not dry)
                self._bridge.post(self._on_clean_done, res, dry)
            except Exception as e:  # noqa: BLE001
                self._bridge.post(lambda exc=e: self._on_clean_error(exc))

        spec = TaskSpec(name="cleaner-run", fn=run)
        self._runner.submit(spec)

    def _on_clean_done(self, res, dry: bool) -> None:
        self._btn_clean_busy = False
        self._btn_clean.setEnabled(True)
        self._btn_clean.setText("Clean selected")
        msg = (f"{'[DRY] ' if dry else ''}Reclaimed "
               f"{fmt_bytes(res.bytes_freed)} across {len(res.records)} items.")
        _show_toast(self, msg, "success")
        _set_status(self, msg)
        self._refresh()

    def _on_clean_error(self, exc) -> None:
        self._btn_clean_busy = False
        self._btn_clean.setEnabled(True)
        self._btn_clean.setText("Clean selected")
        _show_toast(self, f"Clean failed: {exc}", "error")