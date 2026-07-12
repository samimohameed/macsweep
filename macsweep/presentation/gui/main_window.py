"""Main window: scan dashboard with per-target groups and item checkboxes.

Presentation only — every decision about what may be scanned or removed
is made by the domain/application layers behind AppService.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
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
ACCENT = "#4f46e5"
ACCENT_HOVER = "#4338ca"

STYLE = f"""
QPushButton {{
    padding: 7px 18px;
    border-radius: 8px;
    border: 1px solid palette(mid);
    background: palette(button);
    font-size: 13px;
}}
QPushButton:hover {{ background: palette(midlight); }}
QPushButton#primary {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{
    background: palette(mid);
    color: palette(placeholder-text);
}}
QTreeWidget {{
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 4px;
}}
QTreeWidget::item {{ min-height: 26px; }}
QHeaderView::section {{
    background: transparent;
    border: none;
    padding: 6px;
    font-weight: 600;
    color: palette(text);
}}
QProgressBar#sharebar {{
    border: none;
    background: palette(alternate-base);
    border-radius: 3px;
    max-height: 7px;
    min-height: 7px;
}}
QProgressBar#sharebar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QProgressBar#busybar {{
    border: none;
    background: palette(alternate-base);
    border-radius: 3px;
    max-height: 6px;
}}
QProgressBar#busybar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
"""


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


def _tilde(path) -> str:
    text = str(path)
    home = str(Path.home())
    return "~" + text[len(home):] if text.startswith(home) else text


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MacSweep")
        self.resize(900, 640)
        self.setStyleSheet(STYLE)

        self._reporter = SignalReporter()
        self._reporter.message.connect(self._on_status)
        self._app = build_app(self._reporter)
        self._scan_worker: Optional[ScanWorker] = None
        self._clean_worker: Optional[CleanWorker] = None
        self._last_report: Optional[ScanReport] = None
        self._skipped_group: Optional[QTreeWidgetItem] = None

        self._build_ui()

    # ---- UI construction ----

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 10)
        layout.setSpacing(12)

        # Branded header: icon, name + tagline, big reclaimable total.
        header = QHBoxLayout()
        header.setSpacing(12)
        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    52, 52,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            header.addWidget(icon_label)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("MacSweep")
        title.setStyleSheet("font-size: 21px; font-weight: 700;")
        tagline = QLabel("Safe storage cleaner — nothing is deleted, only moved to Trash")
        tagline.setStyleSheet("color: gray; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(tagline)
        header.addLayout(title_box)
        header.addStretch(1)
        total_box = QVBoxLayout()
        total_box.setSpacing(0)
        self.total_label = QLabel("—")
        self.total_label.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {ACCENT};"
        )
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_caption = QLabel("press Scan to begin")
        self.total_caption.setStyleSheet("color: gray; font-size: 11px;")
        self.total_caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        total_box.addWidget(self.total_label)
        total_box.addWidget(self.total_caption)
        header.addLayout(total_box)
        layout.addLayout(header)

        # Action row.
        actions = QHBoxLayout()
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self._start_scan)
        self.clean_btn = QPushButton("Clean selected  →  Trash")
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self._start_clean)
        self.skipped_btn = QPushButton("Show skipped")
        self.skipped_btn.setCheckable(True)
        self.skipped_btn.setEnabled(False)
        self.skipped_btn.setToolTip(
            "Items the scan saw but left alone — and the exact rule that "
            "protected each one (age gate, blocklist, symlink escape, …)."
        )
        self.skipped_btn.toggled.connect(lambda _c: self._render_skipped())
        actions.addWidget(self.scan_btn)
        actions.addWidget(self.clean_btn)
        actions.addWidget(self.skipped_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Size", "", "Age (days)"])
        self.tree.setColumnWidth(0, 470)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 130)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree)

        safety = QLabel(
            "Whitelist-only · never touches system files, apps, or documents · "
            "everything is recoverable from the Trash"
        )
        safety.setStyleSheet("color: gray; font-size: 11px;")
        safety.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(safety)

        self.progress = QProgressBar()
        self.progress.setObjectName("busybar")
        self.progress.setRange(0, 0)  # busy indicator
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

    # ---- scan ----

    def _start_scan(self) -> None:
        self._set_busy(True, "Scanning…")
        self.tree.clear()
        self._skipped_group = None
        self._last_report = None
        self.skipped_btn.setEnabled(False)
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
        total = max(report.total_bytes, 1)
        bold = QFont()
        bold.setBold(True)
        self.tree.blockSignals(True)
        for target_id, items in sorted(
            report.by_target().items(),
            key=lambda kv: -sum(i.size_bytes for i in kv[1]),
        ):
            subtotal = sum(i.size_bytes for i in items)
            group = QTreeWidgetItem(
                [
                    f"{names.get(target_id, target_id)}   ·   {len(items)} items",
                    _human(subtotal),
                    "",
                    "",
                ]
            )
            group.setFont(0, bold)
            group.setFont(1, bold)
            group.setFlags(
                group.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsAutoTristate
            )
            group.setCheckState(0, Qt.CheckState.Checked)
            for item in sorted(items, key=lambda i: -i.size_bytes):
                child = QTreeWidgetItem(
                    [
                        _tilde(item.path),
                        _human(item.size_bytes),
                        "",
                        f"{item.age_days:.0f}",
                    ]
                )
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked)
                child.setData(0, ITEM_ROLE, item)
                child.setToolTip(0, str(item.path))
                group.addChild(child)
            self.tree.addTopLevelItem(group)

            # Proportional share bar so the big categories pop visually.
            bar = QProgressBar()
            bar.setObjectName("sharebar")
            bar.setRange(0, 100)
            bar.setValue(max(2, round(subtotal * 100 / total)))
            bar.setTextVisible(False)
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(4, 10, 12, 10)
            holder_layout.addWidget(bar)
            self.tree.setItemWidget(group, 2, holder)
        self.tree.blockSignals(False)

        self._last_report = report
        self.skipped_btn.setEnabled(bool(report.skipped))
        self.skipped_btn.setText(f"Show skipped ({len(report.skipped):,})")
        self._render_skipped()

        if report.items:
            self.statusBar().showMessage(
                f"Scan finished — {len(report.items)} items eligible, "
                f"{len(report.skipped):,} left alone."
            )
        else:
            self.statusBar().showMessage(
                f"Scan finished — nothing to clean "
                f"({len(report.skipped):,} items protected by the safety rules)."
            )
            self.total_label.setText("0 B")
            self.total_caption.setText("your Mac looks tidy ✨")
        self._refresh_selection_total()

    def _render_skipped(self) -> None:
        """Show/hide the read-only 'skipped items' group at the bottom.
        by listing each skipped item with the exact rule that protected it.
        """
        if self._skipped_group is not None:
            index = self.tree.indexOfTopLevelItem(self._skipped_group)
            if index >= 0:
                self.tree.takeTopLevelItem(index)
            self._skipped_group = None
        if not self.skipped_btn.isChecked() or not self._last_report:
            return
        skipped = self._last_report.skipped
        if not skipped:
            return

        self.tree.blockSignals(True)
        gray = QColor("gray")
        group = QTreeWidgetItem(
            [f"Skipped — protected by safety rules   ·   {len(skipped):,} items",
             "", "", ""]
        )
        font = QFont()
        font.setBold(True)
        group.setFont(0, font)
        for col in range(4):
            group.setForeground(col, gray)
        limit = 300
        for path, reason in skipped[:limit]:
            child = QTreeWidgetItem([_tilde(path), "", "", reason])
            child.setToolTip(0, str(path))
            child.setToolTip(3, reason)
            for col in range(4):
                child.setForeground(col, gray)
            group.addChild(child)
        if len(skipped) > limit:
            more = QTreeWidgetItem(
                [f"… and {len(skipped) - limit:,} more", "", "", ""]
            )
            more.setForeground(0, gray)
            group.addChild(more)
        self.tree.addTopLevelItem(group)
        group.setExpanded(True)
        self._skipped_group = group
        self.tree.blockSignals(False)

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
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, "Moving items to Trash…")
        self._clean_worker = CleanWorker(self._app, items)
        self._clean_worker.progress.connect(
            lambda cur, total, path: self.statusBar().showMessage(
                f"Moving to Trash ({cur}/{total}): {path}"
            )
        )
        self._clean_worker.finished_with.connect(self._on_clean_done)
        self._clean_worker.failed.connect(self._on_worker_failed)
        self._clean_worker.start()

    def _on_clean_done(self, report) -> None:
        self._set_busy(False)
        message = (
            f"Freed {_human(report.freed_bytes)} — "
            f"{len(report.removed)} items moved to Trash.\n"
            "Space is reclaimed for good once you empty the Trash."
        )
        if report.failed:
            details = "\n".join(
                f"• {item.path}: {reason}" for item, reason in report.failed[:8]
            )
            message += f"\n\n{len(report.failed)} items were skipped:\n{details}"
        self.statusBar().showMessage(message.splitlines()[0])
        QMessageBox.information(self, "Done", message)
        self._start_scan()  # refresh the dashboard

    # ---- helpers ----

    def _checked_items(self) -> list[CleanupItem]:
        items: list[CleanupItem] = []
        for g in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(g)
            for c in range(group.childCount()):
                child = group.child(c)
                if child.checkState(0) == Qt.CheckState.Checked:
                    data = child.data(0, ITEM_ROLE)
                    if data is not None:
                        items.append(data)
        return items

    def _refresh_selection_total(self) -> None:
        items = self._checked_items()
        total = sum(i.size_bytes for i in items)
        if items:
            self.total_label.setText(_human(total))
            self.total_caption.setText(f"selected across {len(items):,} items")
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
