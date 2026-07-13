"""Ports (interfaces) for the application layer.

Use cases depend on these abstractions, never on concrete infrastructure.
This is the dependency-inversion boundary of the clean architecture:
infrastructure adapters implement these Protocols and are injected in
at composition time (see presentation/cli.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Protocol


class FileSystemPort(Protocol):
    """Read-only filesystem queries used during scanning."""

    def iter_children(self, root: Path, glob: str) -> Iterator[Path]:
        """Yield immediate children of root matching glob."""
        ...

    def resolve(self, path: Path) -> Path:
        """Resolve symlinks to a real absolute path."""
        ...

    def size_of(self, path: Path) -> int:
        """Total size in bytes (recursive for directories)."""
        ...

    def allocated_size_of(self, path: Path) -> int:
        """Actual disk blocks used (recursive). Differs from size_of for
        sparse files such as Docker's disk image, whose apparent size can
        be hundreds of GB while occupying almost nothing."""
        ...

    def age_days(self, path: Path) -> float:
        """Days since last modification (newest mtime within a directory)."""
        ...

    def exists(self, path: Path) -> bool: ...

    def is_dir(self, path: Path) -> bool:
        """True for real directories (not symlinks to directories)."""
        ...


class RemoverPort(Protocol):
    """The only interface through which anything is ever removed."""

    def remove(self, path: Path) -> None:
        """Remove a file/directory. Implementations should prefer
        recoverable removal (move to Trash) over permanent deletion."""
        ...


class ReporterPort(Protocol):
    """Output boundary so use cases never print directly."""

    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
