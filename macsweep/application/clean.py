"""Clean use case.

The single code path through which anything is ever removed.
Re-validates every item against the SafetyPolicy immediately before
removal (time-of-check vs time-of-use protection), and honors dry-run.
"""
from __future__ import annotations

from ..domain.entities import CleanReport, CleanupItem, CleanupTarget
from ..domain.policies import SafetyPolicy
from .ports import FileSystemPort, RemoverPort, ReporterPort


class CleanUseCase:
    def __init__(
        self,
        fs: FileSystemPort,
        remover: RemoverPort,
        policy: SafetyPolicy,
        reporter: ReporterPort,
    ) -> None:
        self._fs = fs
        self._remover = remover
        self._policy = policy
        self._reporter = reporter

    def execute(
        self,
        items: list[CleanupItem],
        targets: dict[str, CleanupTarget],
        dry_run: bool = True,
    ) -> CleanReport:
        report = CleanReport(dry_run=dry_run)

        for item in items:
            target = targets.get(item.target_id)
            if target is None:
                report.failed.append((item, "unknown target (refusing)"))
                continue

            # Re-validate at removal time: the filesystem may have changed
            # between scan and clean (files replaced with symlinks, etc.).
            try:
                if not self._fs.exists(item.path):
                    continue  # already gone; nothing to do
                resolved = self._fs.resolve(item.path)
                resolved_root = self._fs.resolve(target.root)
            except OSError as exc:
                report.failed.append((item, str(exc)))
                continue

            reason = self._policy.validate(resolved, resolved_root)
            if reason is None:
                age = self._fs.age_days(resolved)
                reason = self._policy.validate_age(age, target.min_age_days)
            if reason:
                report.failed.append((item, f"blocked by safety policy: {reason}"))
                continue

            if dry_run:
                report.removed.append(item)
                continue

            try:
                self._remover.remove(resolved)
                report.removed.append(item)
            except PermissionError:
                report.failed.append((item, "permission denied"))
            except OSError as exc:
                report.failed.append((item, str(exc)))

        return report
