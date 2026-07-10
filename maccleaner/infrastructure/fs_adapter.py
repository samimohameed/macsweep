"""Concrete filesystem adapter (implements FileSystemPort)."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterator


class LocalFileSystem:
    def iter_children(self, root: Path, glob: str) -> Iterator[Path]:
        try:
            yield from sorted(root.glob(glob))
        except (PermissionError, OSError):
            return

    def resolve(self, path: Path) -> Path:
        return path.resolve(strict=True)

    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir() and not path.is_symlink()

    def size_of(self, path: Path) -> int:
        if path.is_file() or path.is_symlink():
            try:
                return path.lstat().st_size
            except OSError:
                return 0
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
            for name in filenames:
                try:
                    total += os.lstat(os.path.join(dirpath, name)).st_size
                except OSError:
                    continue
        return total

    def age_days(self, path: Path) -> float:
        """Days since the *newest* modification anywhere inside the path.

        Using the newest mtime (not the root's) means a cache directory
        that an app wrote to yesterday is treated as 1 day old, even if
        the directory itself was created a year ago.
        """
        newest = self._newest_mtime(path)
        return max(0.0, (time.time() - newest) / 86_400)

    def _newest_mtime(self, path: Path) -> float:
        try:
            newest = path.lstat().st_mtime
        except OSError:
            return time.time()  # unreadable -> treat as brand new (skipped)
        if path.is_dir() and not path.is_symlink():
            for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
                for name in filenames:
                    try:
                        mtime = os.lstat(os.path.join(dirpath, name)).st_mtime
                        if mtime > newest:
                            newest = mtime
                    except OSError:
                        continue
        return newest
