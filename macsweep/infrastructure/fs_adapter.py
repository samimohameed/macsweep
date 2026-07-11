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

        The ctime (last inode change on this disk) is considered alongside
        the mtime: downloaders such as Homebrew's preserve the *server's*
        modification time, so a bottle fetched an hour ago can carry an
        mtime from months back — and macOS backdates st_birthtime along
        with it. ctime cannot be backdated from userspace, so it reliably
        reflects when the file actually appeared here; without it the age
        gate would sweep freshly downloaded files.
        """
        newest = self._newest_timestamp(path)
        return max(0.0, (time.time() - newest) / 86_400)

    @staticmethod
    def _stat_timestamp(st: os.stat_result) -> float:
        return max(st.st_mtime, st.st_ctime)

    def _newest_timestamp(self, path: Path) -> float:
        try:
            newest = self._stat_timestamp(path.lstat())
        except OSError:
            return time.time()  # unreadable -> treat as brand new (skipped)
        if path.is_dir() and not path.is_symlink():
            for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
                for name in filenames:
                    try:
                        ts = self._stat_timestamp(
                            os.lstat(os.path.join(dirpath, name))
                        )
                        if ts > newest:
                            newest = ts
                    except OSError:
                        continue
        return newest
