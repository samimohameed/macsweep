"""Registry of known large tool-managed stores (for the Insights feature).

These are places where gigabytes commonly accumulate but which MacSweep
must never touch — they hold live application state (containers, device
backups, simulators). Instead of deleting, MacSweep measures them and
points the user at the owning tool's own safe reclaim command.

Detection is read-only. Adding an entry here can never make anything
deletable: insights have no removal path at all.
"""
from __future__ import annotations

from pathlib import Path

from ..domain.entities import Insight

HOME = Path.home()
GB = 1024 * 1024 * 1024
MB = 1024 * 1024


def default_insights() -> list[Insight]:
    return [
        Insight(
            id="docker-data",
            title="Docker Desktop data",
            path=HOME / "Library" / "Containers" / "com.docker.docker" / "Data",
            explanation="Holds your images, containers, and volumes — live "
                        "application data, so MacSweep never touches it. "
                        "Docker can safely remove only what is unused.",
            command="docker system prune",
            min_bytes=500 * MB,
        ),
        Insight(
            id="ios-simulators",
            title="iOS Simulator devices",
            path=HOME / "Library" / "Developer" / "CoreSimulator" / "Devices",
            explanation="Simulator devices contain installed apps and their "
                        "data. Xcode's own tool can delete just the ones no "
                        "longer usable with your installed runtimes.",
            command="xcrun simctl delete unavailable",
            min_bytes=1 * GB,
        ),
        Insight(
            id="ios-backups",
            title="iPhone/iPad backups",
            path=HOME / "Library" / "Application Support" / "MobileSync" / "Backup",
            explanation="Device backups are irreplaceable user data — "
                        "MacSweep will never touch them. Review and delete "
                        "old ones where you can see what each backup is.",
            command="Finder → select your device → Manage Backups…",
            copyable=False,
            min_bytes=1 * GB,
        ),
        Insight(
            id="trash",
            title="Trash",
            path=HOME / ".Trash",
            explanation="Everything MacSweep cleans lands here so it stays "
                        "recoverable. The space is only truly freed once you "
                        "empty it.",
            command="Finder → Empty Trash",
            copyable=False,
            min_bytes=200 * MB,
        ),
    ]
