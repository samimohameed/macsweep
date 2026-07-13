"""Main window: scan dashboard with per-target groups and item checkboxes.

Presentation only — every decision about what may be scanned or removed
is made by the domain/application layers behind AppService.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...composition import build_app
from ...domain.entities import CleanupItem, ScanReport
from .workers import CleanWorker, InsightsWorker, ScanWorker, SignalReporter

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
/* Two surfaces: branded indigo sidebar, white content. Panels are white
   with a consistent border; the banner is an accent tint. */
#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #312e81, stop:1 #4338ca);
}}
#content {{
    background: palette(base);
}}
#sidebar QLabel {{ color: white; }}
QListWidget#nav {{
    border: none;
    background: transparent;
    outline: none;
    color: rgba(255, 255, 255, 0.85);
}}
QListWidget#nav::item {{
    min-height: 36px;
    border-radius: 8px;
    padding: 2px 10px;
    font-size: 14px;
}}
QListWidget#nav::item:selected {{
    background: rgba(255, 255, 255, 0.22);
    color: white;
    font-weight: 600;
}}
QListWidget#nav::item:hover:!selected {{
    background: rgba(255, 255, 255, 0.10);
}}
QListWidget#insightsList {{
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 4px;
}}
QListWidget#insightsList::item {{
    min-height: 44px;
    border-radius: 6px;
    padding: 4px 8px;
}}
QListWidget#insightsList::item:selected {{ background: {ACCENT}; color: white; }}
QLabel#detailPane {{
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 14px;
    background: palette(base);
}}
QLabel#banner {{
    background: rgba(79, 70, 229, 0.08);
    border-left: 3px solid {ACCENT};
    border-radius: 6px;
    padding: 10px 12px;
    color: palette(text);
}}
QLabel#pageTitle {{ font-size: 17px; font-weight: 700; }}
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
        self._insights_worker: Optional[InsightsWorker] = None

        self._build_ui()

    # ---- UI construction ----

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Sidebar: brand, navigation, safety promise ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(14)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        icon_path = Path(__file__).parent / "assets" / "icon.png"
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    36, 36,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            brand.addWidget(icon_label)
        brand_name = QLabel("MacSweep")
        brand_name.setStyleSheet("font-size: 17px; font-weight: 700;")
        brand.addWidget(brand_name)
        brand.addStretch(1)
        side.addLayout(brand)

        assets = Path(__file__).parent / "assets"
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(18, 18))
        self.nav.addItem(
            QListWidgetItem(QIcon(str(assets / "nav-cleanup.svg")), "Cleanup")
        )
        self.nav.addItem(
            QListWidgetItem(QIcon(str(assets / "nav-insights.svg")), "Insights")
        )
        self.nav.setCurrentRow(0)
        side.addWidget(self.nav, 1)

        safety = QLabel(
            "Whitelist-only. Never touches system files, apps, or documents. "
            "Everything is recoverable from the Trash."
        )
        safety.setStyleSheet(
            "color: rgba(255, 255, 255, 0.65); font-size: 11px;"
        )
        safety.setWordWrap(True)
        side.addWidget(safety)
        outer.addWidget(sidebar)

        # --- Content area ---
        content = QWidget()
        content.setObjectName("content")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 10)
        layout.setSpacing(12)

        # --- Cleanup page: title + total, action row, results tree ---
        cleanup_page = QWidget()
        cleanup_layout = QVBoxLayout(cleanup_page)
        cleanup_layout.setContentsMargins(0, 0, 0, 0)
        cleanup_layout.setSpacing(12)

        cleanup_header = QHBoxLayout()
        cleanup_title = QLabel("Cleanup")
        cleanup_title.setObjectName("pageTitle")
        cleanup_header.addWidget(cleanup_title)
        cleanup_header.addStretch(1)
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
        cleanup_header.addLayout(total_box)
        cleanup_layout.addLayout(cleanup_header)

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
        cleanup_layout.addLayout(actions)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item", "Size", "", "Age (days)"])
        self.tree.setColumnWidth(0, 360)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 120)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        cleanup_layout.addWidget(self.tree)

        # --- Insights page: explainer banner + master list + detail pane ---
        insights_page = QWidget()
        insights_outer = QVBoxLayout(insights_page)
        insights_outer.setContentsMargins(0, 0, 0, 0)
        insights_outer.setSpacing(12)

        insights_title = QLabel("Insights")
        insights_title.setObjectName("pageTitle")
        insights_outer.addWidget(insights_title)

        banner = QLabel(
            "<b>Found, measured — but deliberately not touched.</b> "
            "These stores belong to other tools (Docker, Xcode, Finder) and "
            "may contain your work: images, simulators, device backups. "
            "MacSweep never deletes what it can't guarantee is safe — so "
            "instead it shows the real space used and each tool's own safe "
            "reclaim command. You stay in control."
        )
        banner.setObjectName("banner")
        banner.setWordWrap(True)
        insights_outer.addWidget(banner)

        insights_layout = QHBoxLayout()
        insights_layout.setSpacing(12)
        insights_outer.addLayout(insights_layout, 1)

        self.insights_list = QListWidget()
        self.insights_list.setObjectName("insightsList")
        self.insights_list.currentItemChanged.connect(self._show_insight_detail)
        insights_layout.addWidget(self.insights_list, 2)

        detail_col = QVBoxLayout()
        detail_col.setSpacing(8)
        self.insight_detail = QLabel(
            "Big tool-managed stores MacSweep deliberately won't touch.\n\n"
            "Select an item to see what it is and the owning tool's own "
            "safe way to reclaim the space."
        )
        self.insight_detail.setObjectName("detailPane")
        self.insight_detail.setWordWrap(True)
        self.insight_detail.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.insight_detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        detail_col.addWidget(self.insight_detail, 1)
        self.copy_cmd_btn = QPushButton("Copy command")
        self.copy_cmd_btn.hide()
        self.copy_cmd_btn.clicked.connect(self._copy_selected_command)
        detail_col.addWidget(self.copy_cmd_btn, 0, Qt.AlignmentFlag.AlignRight)
        insights_layout.addLayout(detail_col, 3)

        self.stack = QStackedWidget()
        self.stack.addWidget(cleanup_page)
        self.stack.addWidget(insights_page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.stack, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("busybar")
        self.progress.setRange(0, 0)  # busy indicator
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        outer.addWidget(content, 1)
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

        # Measure the big stores we refuse to touch, in the background.
        self._insights_worker = InsightsWorker(self._app)
        self._insights_worker.finished_with.connect(self._on_insights)
        self._insights_worker.start()

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

    # ---- insights ----

    def _on_insights(self, insights: list) -> None:
        self.insights_list.clear()
        if not insights:
            self.nav.item(1).setText("Insights")
            self.insight_detail.setText(
                "No large tool-managed stores found right now.\n\n"
                "This tab lists things like Docker data, iOS Simulators, and "
                "device backups — stores MacSweep deliberately won't touch — "
                "with the owning tool's own safe reclaim command."
            )
            self.copy_cmd_btn.hide()
            return

        total = sum(i.size_bytes for i in insights)
        self.nav.item(1).setText(f"Insights · {_human(total)}")
        for ins in insights:
            item = QListWidgetItem(f"{ins.title}\n{_human(ins.size_bytes)}")
            item.setData(ITEM_ROLE, ins)
            item.setToolTip(str(ins.path))
            self.insights_list.addItem(item)
        self.insights_list.setCurrentRow(0)

    def _show_insight_detail(self, current, _previous=None) -> None:
        ins = current.data(ITEM_ROLE) if current else None
        if ins is None:
            self.copy_cmd_btn.hide()
            return
        how = "Run in Terminal:" if ins.copyable else "How to reclaim:"
        self.insight_detail.setText(
            f"<h3 style='margin:0'>{ins.title} — "
            f"<span style='color:{ACCENT};'>{_human(ins.size_bytes)}</span></h3>"
            f"<p style='color:gray; font-size:12px;'>{ins.path}</p>"
            f"<p>{ins.explanation}</p>"
            f"<p><b>{how}</b><br><code style='font-size:13px;'>{ins.command}"
            f"</code></p>"
        )
        self.copy_cmd_btn.setVisible(ins.copyable)

    def _copy_selected_command(self) -> None:
        current = self.insights_list.currentItem()
        ins = current.data(ITEM_ROLE) if current else None
        if ins is not None:
            QApplication.clipboard().setText(ins.command)
            self.statusBar().showMessage(f"Copied: {ins.command}", 4000)

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
