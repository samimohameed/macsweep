"""Safety policy.

A second, independent line of defense. Even if a CleanupTarget were
misconfigured, SafetyPolicy.validate() must still reject any path that
could harm the OS, installed applications, or user data.

Defense in depth:
  1. Whitelist  -> only registered targets are ever scanned (entities.py).
  2. Blocklist  -> this module rejects protected prefixes outright.
  3. Age gate   -> recently-modified items are never touched.
  4. Containment-> resolved paths must remain inside the target root
                   (defeats symlink escapes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_protected_prefixes() -> tuple[Path, ...]:
    home = Path.home()
    return (
        # --- Operating system ---
        Path("/System"),
        Path("/Library"),          # system-level Library (NOT ~/Library)
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/etc"),
        Path("/var"),
        Path("/private"),
        Path("/opt"),
        Path("/cores"),
        Path("/dev"),
        Path("/Volumes"),          # external drives / Time Machine
        # --- Installed applications ---
        Path("/Applications"),
        home / "Applications",
        # --- User data ---
        home / "Documents",
        home / "Desktop",
        home / "Downloads",        # cleaning Downloads is deliberately excluded
        home / "Pictures",
        home / "Movies",
        home / "Music",
        home / "Library" / "Mobile Documents",   # iCloud Drive
        home / "Library" / "CloudStorage",       # Dropbox/GDrive/OneDrive mounts
        home / "Library" / "Application Support",  # app data & settings
        home / "Library" / "Preferences",
        home / "Library" / "Keychains",
        home / "Library" / "Mail",
        home / "Library" / "Messages",
        home / "Library" / "Photos",
        home / "Library" / "Containers",
        home / "Library" / "Group Containers",
    )


@dataclass(frozen=True)
class SafetyPolicy:
    """Validates every path immediately before any destructive action."""

    protected_prefixes: tuple[Path, ...] = field(
        default_factory=_default_protected_prefixes
    )

    def _is_under(self, path: Path, prefix: Path) -> bool:
        try:
            path.relative_to(prefix)
            return True
        except ValueError:
            return False

    def validate(self, path: Path, target_root: Path) -> str | None:
        """Return None if the path is safe to remove, else a rejection reason.

        `path` must be the fully resolved (realpath) candidate.
        `target_root` must be the fully resolved root of its CleanupTarget.
        """
        if not path.is_absolute():
            return "path is not absolute"

        if path == Path("/") or path == Path.home():
            return "refusing to touch / or home directory"

        # Containment: after resolving symlinks the item must still live
        # inside its target root. Blocks symlink-escape attacks where a
        # cache entry links out to real user data.
        if not self._is_under(path, target_root):
            return "resolved path escapes its target root (possible symlink)"

        if path == target_root:
            return "refusing to delete the target root itself"

        # Blocklist: reject anything under a protected prefix, regardless
        # of how it was reached.
        for prefix in self.protected_prefixes:
            if self._is_under(path, prefix):
                return f"path is under protected location {prefix}"

        return None

    def validate_age(self, age_days: float, min_age_days: int) -> str | None:
        if age_days < min_age_days:
            return (
                f"modified {age_days:.1f} days ago "
                f"(minimum age is {min_age_days} days)"
            )
        return None
