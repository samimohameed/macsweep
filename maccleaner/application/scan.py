"""Scan use case.

Read-only. Walks registered targets, applies the SafetyPolicy and age
gate to every candidate, and produces a ScanReport. Nothing is removed
here under any circumstances.
"""
from __future__ import annotations

from ..domain.entities import CleanupItem, CleanupTarget, ScanReport
from ..domain.policies import SafetyPolicy
from .ports import FileSystemPort


class ScanUseCase:
    def __init__(self, fs: FileSystemPort, policy: SafetyPolicy) -> None:
        self._fs = fs
        self._policy = policy

    def execute(self, targets: list[CleanupTarget]) -> ScanReport:
        report = ScanReport()

        for target in targets:
            if not self._fs.exists(target.root):
                continue  # target simply not present on this machine

            try:
                resolved_root = self._fs.resolve(target.root)
            except OSError as exc:
                report.errors.append((target.root, str(exc)))
                continue

            for child in self._fs.iter_children(target.root, target.glob):
                try:
                    resolved = self._fs.resolve(child)

                    reason = self._policy.validate(resolved, resolved_root)
                    if reason:
                        report.skipped.append((child, reason))
                        continue

                    age = self._fs.age_days(resolved)
                    reason = self._policy.validate_age(age, target.min_age_days)
                    if reason:
                        report.skipped.append((child, reason))
                        continue

                    size = self._fs.size_of(resolved)
                    if size == 0:
                        continue

                    report.items.append(
                        CleanupItem(
                            target_id=target.id,
                            path=resolved,
                            size_bytes=size,
                            age_days=age,
                        )
                    )
                except PermissionError:
                    report.skipped.append((child, "permission denied"))
                except OSError as exc:
                    report.errors.append((child, str(exc)))

        return report
