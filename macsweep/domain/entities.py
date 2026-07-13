"""Domain entities.

Pure business objects. No I/O, no framework imports, no side effects.
This layer knows nothing about the filesystem, the CLI, or macOS APIs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Risk(Enum):
    """How safe it is to remove items from a target.

    SAFE     -> regenerated automatically by apps/OS (caches, logs).
    MODERATE -> safe but may cost the user something (re-download, re-index).
    OPT_IN   -> only cleaned when the user explicitly asks (e.g. Trash).
    """

    SAFE = "safe"
    MODERATE = "moderate"
    OPT_IN = "opt-in"


@dataclass(frozen=True)
class CleanupTarget:
    """A single known-safe location that may be cleaned.

    Targets are the *only* entry points into the filesystem. If a path is
    not under a registered target, the application can never touch it.
    """

    id: str                      # stable identifier, e.g. "user-caches"
    name: str                    # human readable name
    description: str             # what it is and why it's safe
    root: Path                   # directory whose *contents* are candidates
    risk: Risk = Risk.SAFE
    min_age_days: int = 7        # never touch items modified more recently
    delete_root_itself: bool = False  # we clean contents, never the root
    glob: str = "*"              # pattern for candidate selection inside root

    def __post_init__(self) -> None:
        if not self.root.is_absolute():
            raise ValueError(f"Target root must be absolute: {self.root}")


@dataclass(frozen=True)
class CleanupItem:
    """A concrete file/directory found under a target during a scan."""

    target_id: str
    path: Path
    size_bytes: int
    age_days: float


@dataclass
class ScanReport:
    """Result of scanning one or more targets."""

    items: list[CleanupItem] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)  # (path, reason)
    errors: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(i.size_bytes for i in self.items)

    def by_target(self) -> dict[str, list[CleanupItem]]:
        grouped: dict[str, list[CleanupItem]] = {}
        for item in self.items:
            grouped.setdefault(item.target_id, []).append(item)
        return grouped


@dataclass(frozen=True)
class Insight:
    """A large tool-managed store MacSweep deliberately will not touch,
    plus the tool's own safe way to reclaim it.

    Insights are read-only by definition: MacSweep only measures the
    location and points the user at the owning tool's native command.
    """

    id: str
    title: str
    path: Path
    explanation: str          # why MacSweep refuses to touch it
    command: str              # the safe, native way to reclaim it
    copyable: bool = True     # False when `command` is an instruction, not shell
    min_bytes: int = 100 * 1024 * 1024   # hide below this size
    size_bytes: int = 0       # filled in at scan time


@dataclass
class CleanReport:
    """Result of executing a clean operation."""

    removed: list[CleanupItem] = field(default_factory=list)
    failed: list[tuple[CleanupItem, str]] = field(default_factory=list)
    dry_run: bool = True

    @property
    def freed_bytes(self) -> int:
        return sum(i.size_bytes for i in self.removed)
