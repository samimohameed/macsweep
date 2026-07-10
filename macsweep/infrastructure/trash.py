"""Removers (implement RemoverPort).

TrashRemover is the default: items are moved to the user's Trash via
Finder, so every action is recoverable. PermanentRemover exists only
for the explicit --permanent flag and still never touches anything the
SafetyPolicy hasn't approved.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


class TrashRemover:
    """Move items to Trash. Uses Finder scripting (native, respects macOS
    'put back' metadata) while it stays fast and permitted, then switches
    to a direct move into ~/.Trash — still fully recoverable, just without
    the 'put back' menu entry.

    The switch matters for two reasons: Finder scripting needs an
    Automation permission grant (denied/unanswered prompts stall each call
    until timeout), and at ~0.2s per AppleEvent a large batch would take
    hours. A small time budget gives typical cleans the native path and
    big ones the fast path.
    """

    FINDER_TIME_BUDGET_SECONDS = 5.0

    def __init__(self) -> None:
        self._finder_available = True
        self._finder_seconds_spent = 0.0

    def remove(self, path: Path) -> None:
        if (
            self._finder_available
            and self._finder_seconds_spent < self.FINDER_TIME_BUDGET_SECONDS
        ):
            started = time.monotonic()
            try:
                self._finder_trash(path)
                self._finder_seconds_spent += time.monotonic() - started
                return
            except (subprocess.SubprocessError, OSError):
                self._finder_available = False
        self._fallback_move(path)

    def _finder_trash(self, path: Path) -> None:
        script = (
            'tell application "Finder" to delete POSIX file "{}"'.format(
                str(path).replace('"', '\\"')
            )
        )
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            timeout=10,
        )

    def _fallback_move(self, path: Path) -> None:
        trash = Path.home() / ".Trash"
        trash.mkdir(exist_ok=True)
        dest = trash / path.name
        counter = 0
        while dest.exists() or dest.is_symlink():
            counter += 1
            dest = trash / f"{path.name}-{int(time.time() * 1000)}-{counter}"
        shutil.move(str(path), str(dest))


class PermanentRemover:
    """Irreversible deletion. Only wired in when the user passes
    --permanent explicitly."""

    def remove(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
