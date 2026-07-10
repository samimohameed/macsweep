"""Main window: scan dashboard with per-target groups and item checkboxes.

Presentation only — every decision about what may be scanned or removed
is made by the domain/application layers behind AppService.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...composition import build_app
from ...domain.entities import CleanupItem, ScanReport
from .workers import CleanWorker, ScanWorker, SignalReporter

ITEM_ROLE = Qt.ItemDataRole.UserRole


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MacCleaner — safe, recoverable cleaning")
        self.resize(860, 620)

        self._reporter = SignalReporter()
        self._reporter.message.connect(self._on_status)
        self._app = build_app(self._reporter)
        self._scan_worker: Optional[ScanWorker] = None
        self._clean_worker: Optional[CleanWorker] = None

        self._build_ui()

    # ---- UI construction ----

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        header = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._start_scan)
        self.clean_btn = QPushButton("Clean selected (moves to Trash)")
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self._start_clean)
        self.total_label = QLabel("Press Scan to find reclaimable space.")
        header.addWidget(self.scan_btn)
        header.addWidget(self.clean_btn)
        header.addStretch(1)
        header.addWidget(self.total_label)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Size", "Age (days)"])
        self.tree.setColumnWidth(0, 560)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        safety = QLabel(
            "Whitelist-only · never touches system files, apps, or documents · "
            "everything goes to the Trash and is recoverable."
        )
        safety.setStyleSheet("color: gray;")
        layout.addWidget(safety)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # busy indicator
        self.progress.hide()
        layout.addWidget(self.progress)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

    # ---- scan ----

    def _start_scan(self) -> None:
        self._set_busy(True, "Scanning…")
        self.tree.clear()
        targets = self._app.select_targets()  # safe defaults; no opt-in targets
        self._scan_worker = ScanWorker(self._app, targets)
        self._scan_worker.target_started.connect(
            lambda name: self.statusBar().showMessage(f"Scanning {name}…")
        )
        self._scan_worker.finished_with.connect(self._on_scan_done)
        self._scan_worker.failed.connect(self._on_worker_failed)
        self._scan_worker.start()

    def _on_scan_done(self, report: ScanReport) -> None:
        self._set_busy(False)
        names = {t.id: t.name for t in self._app.list_targets()}
        self.tree.blockSignals(True)
        for target_id, items in sorted(
            report.by_target().items(),
            key=lambda kv: -sum(i.size_bytes for i in kv[1]),
        ):
            subtotal = sum(i.size_bytes for i in items)
            group = QTreeWidgetItem(
                [names.get(target_id, target_id), _human(subtotal), ""]
            )
            group.setFlags(
                group.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            group.setCheckState(0, Qt.CheckState.Checked)
            for item in sorted(items, key=lambda i: -i.size_bytes):
                child = QTreeWidgetItem(
                    [str(item.path), _human(item.size_bytes), f"{item.age_days:.0f}"]
                )
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked)
                child.setData(0, ITEM_ROLE, item)
                group.addChild(child)
            self.tree.addTopLevelItem(group)
        self.tree.blockSignals(False)

        if report.items:
            self.statusBar().showMessage(
                f"Scan finished — {len(report.items)} items eligible."
            )
        else:
            self.statusBar().showMessage("Scan finished — nothing to clean.")
            self.total_label.setText("Your Mac looks tidy. ✨")
        self._refresh_selection_total()

    # ---- clean ----

    def _start_clean(self) -> None:
        items = self._checked_items()
        if not items:
            return
        total = sum(i.size_bytes for i in items)
        answer = QMessageBox.question(
            self,
            "Move to Trash?",
            f"Move {len(items)} items ({_human(total)}) to the Trash?\n\n"
            "Everything stays recoverable until you empty the Trash yourself.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, "Moving items to Trash…")
        self._clean_worker = CleanWorker(self._app, items)
        self._clean_worker.finished_with.connect(self._on_clean_done)
        self._clean_worker.failed.connect(self._on_worker_failed)
        self._clean_worker.start()

    def _on_clean_done(self, report) -> None:
        self._set_busy(False)
        message = (
            f"Freed {_human(report.freed_bytes)} — "
            f"{len(report.removed)} items moved to Trash."
        )
        if report.failed:
            message += f" ({len(report.failed)} skipped/blocked.)"
        self.statusBar().showMessage(message)
        QMessageBox.information(self, "Done", message)
        self._start_scan()  # refresh the dashboard

    # ---- helpers ----

    def _checked_items(self) -> list[CleanupItem]:
        items: list[CleanupItem] = []
        for g in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(g)
            for c in range(group.childCount()):
                child = group.child(c)
                if child.checkState(0) is Qt.CheckState.Checked:
                    data = child.data(0, ITEM_ROLE)
                    if data is not None:
                        items.append(data)
        return items

    def _refresh_selection_total(self) -> None:
        items = self._checked_items()
        total = sum(i.size_bytes for i in items)
        if items:
            self.total_label.setText(
                f"Selected: {_human(total)} across {len(items)} items"
            )
        self.clean_btn.setEnabled(bool(items) and not self.progress.isVisible())

    def _on_item_changed(self, _item, _column) -> None:
        self._refresh_selection_total()

    def _on_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _on_worker_failed(self, error: str) -> None:
        self._set_busy(False)
        QMessageBox.warning(self, "Error", error)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress.setVisible(busy)
        self.scan_btn.setEnabled(not busy)
        self.clean_btn.setEnabled(not busy and bool(self._checked_items()))
        if message:
            self.statusBar().showMessage(message)
