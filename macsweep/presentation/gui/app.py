"""GUI entry point.

Kept import-light so `macsweep gui` fails with a helpful message when
PySide6 (an optional dependency) is missing.
"""
from __future__ import annotations

import sys


def run_gui() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "The desktop app requires PySide6. Install it with:\n"
            "    python3 -m pip install 'macsweep[gui]'\n"
            "or: python3 -m pip install PySide6",
            file=sys.stderr,
        )
        return 1

    from pathlib import Path

    from PySide6.QtGui import QIcon

    from .main_window import MainWindow

    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName("MacSweep")
    qt_app.setApplicationDisplayName("MacSweep")
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.exists():
        qt_app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return qt_app.exec()
