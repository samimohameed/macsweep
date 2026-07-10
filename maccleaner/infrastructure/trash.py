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
    """Move items to Trash using Finder (native, recoverable, respects
    macOS 'put back' metadata). Falls back to a manual move into
    ~/.Trash if Finder scripting is unavailable."""

    def remove(self, path: Path) -> None:
        try:
            self._finder_trash(path)
        except (subprocess.SubprocessError, OSError):
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
            timeout=30,
        )

    def _fallback_move(self, path: Path) -> None:
        trash = Path.home() / ".Trash"
        trash.mkdir(exist_ok=True)
        dest = trash / path.name
        if dest.exists():
            dest = trash / f"{path.name}-{int(time.time() * 1000)}"
        shutil.move(str(path), str(dest))


class PermanentRemover:
    """Irreversible deletion. Only wired in when the user passes
    --permanent explicitly."""

    def remove(self, path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
