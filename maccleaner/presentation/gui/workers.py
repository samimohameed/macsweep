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


class CleanWorker(QThread):
    finished_with = Signal(CleanReport)
    failed = Signal(str)

    def __init__(self, app: AppService, items: list[CleanupItem]) -> None:
        super().__init__()
        self._app = app
        self._items = items

    def run(self) -> None:
        try:
            # The GUI always moves items to Trash (recoverable); permanent
            # deletion is deliberately CLI-only.
            report = self._app.clean(self._items, dry_run=False, permanent=False)
            self.finished_with.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))
