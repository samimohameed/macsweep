"""Background workers so scans and cleans never block the UI thread.

Workers talk to the same AppService facade as the CLI; results come back
to the main thread via Qt signals.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from ...application.app_service import AppService
from ...domain.entities import CleanReport, CleanupItem, CleanupTarget, ScanReport


class SignalReporter(QObject):
    """ReporterPort implementation that forwards messages as Qt signals."""

    message = Signal(str)

    def info(self, message: str) -> None:
        self.message.emit(message)

    def warn(self, message: str) -> None:
        self.message.emit(f"⚠️ {message}")


class ScanWorker(QThread):
    target_started = Signal(str)   # target name
    finished_with = Signal(ScanReport)
    failed = Signal(str)

    def __init__(self, app: AppService, targets: list[CleanupTarget]) -> None:
        super().__init__()
        self._app = app
        self._targets = targets

    def run(self) -> None:
        try:
            report = self._app.scan(
                self._targets,
                progress=lambda t: self.target_started.emit(t.name),
            )
            self.finished_with.emit(report)
        except Exception as exc:  # surface, never crash the UI thread
            self.failed.emit(str(exc))


class InsightsWorker(QThread):
    """Measures known tool-managed stores (read-only; can take a moment
    for multi-GB directories) off the UI thread."""

    finished_with = Signal(list)  # list[Insight]
    failed = Signal(str)

    def __init__(self, app: AppService) -> None:
        super().__init__()
        self._app = app

    def run(self) -> None:
        try:
            self.finished_with.emit(self._app.insights())
        except Exception as exc:
            self.failed.emit(str(exc))


class CleanWorker(QThread):
    progress = Signal(int, int, str)  # current, total, path
    finished_with = Signal(CleanReport)
    failed = Signal(str)

    def __init__(self, app: AppService, items: list[CleanupItem]) -> None:
        super().__init__()
        self._app = app
        self._items = items

    def run(self) -> None:
        try:
            # The GUI always moves items to Trash (recoverable); permanent
            # deletion is deliberately CLI-only. Items are cleaned one at a
            # time so the UI can show which path is being moved.
            merged = CleanReport(dry_run=False)
            total = len(self._items)
            for index, item in enumerate(self._items, start=1):
                # Throttle UI updates on huge batches.
                if total <= 100 or index % 50 == 0 or index == total:
                    self.progress.emit(index, total, str(item.path))
                report = self._app.clean([item], dry_run=False, permanent=False)
                merged.removed.extend(report.removed)
                merged.failed.extend(report.failed)
            self.finished_with.emit(merged)
        except Exception as exc:
            self.failed.emit(str(exc))
