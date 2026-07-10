"""Application facade shared by every presentation layer (CLI, GUI, …).

Bundles target selection, scanning, and cleaning behind one object so
presentation layers contain no business logic. Depends only on domain
entities and the application ports; concrete adapters are injected by
the composition root (macsweep/composition.py).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from ..domain.entities import (
    CleanReport,
    CleanupItem,
    CleanupTarget,
    Risk,
    ScanReport,
)
from ..domain.policies import SafetyPolicy
from .clean import CleanUseCase
from .ports import FileSystemPort, RemoverPort, ReporterPort
from .scan import ScanUseCase


class AppService:
    def __init__(
        self,
        fs: FileSystemPort,
        policy: SafetyPolicy,
        reporter: ReporterPort,
        all_targets: list[CleanupTarget],
        trash_remover: RemoverPort,
        permanent_remover: RemoverPort,
    ) -> None:
        self._fs = fs
        self._policy = policy
        self._reporter = reporter
        self._all_targets = list(all_targets)
        self._trash_remover = trash_remover
        self._permanent_remover = permanent_remover

    # ---- targets ----

    def list_targets(self) -> list[CleanupTarget]:
        return list(self._all_targets)

    def select_targets(
        self,
        include_opt_in: Optional[list[str]] = None,
        only: Optional[list[str]] = None,
        min_age_days: Optional[int] = None,
    ) -> list[CleanupTarget]:
        """Apply the standard selection rules.

        Opt-in targets are excluded unless explicitly listed; a min-age
        override can only raise a target's built-in minimum, never lower it.
        """
        include_opt_in = include_opt_in or []
        targets = [
            t for t in self._all_targets
            if t.risk is not Risk.OPT_IN or t.id in include_opt_in
        ]
        if only:
            targets = [t for t in targets if t.id in only]
        if min_age_days is not None:
            targets = [
                replace(t, min_age_days=max(t.min_age_days, min_age_days))
                for t in targets
            ]
        return targets

    # ---- use cases ----

    def scan(
        self,
        targets: list[CleanupTarget],
        progress: Optional[Callable[[CleanupTarget], None]] = None,
    ) -> ScanReport:
        """Read-only scan. `progress` is called before each target."""
        use_case = ScanUseCase(self._fs, self._policy)
        if progress is None:
            return use_case.execute(targets)
        report = ScanReport()
        for target in targets:
            progress(target)
            partial = use_case.execute([target])
            report.items.extend(partial.items)
            report.skipped.extend(partial.skipped)
            report.errors.extend(partial.errors)
        return report

    def clean(
        self,
        items: list[CleanupItem],
        dry_run: bool = True,
        permanent: bool = False,
    ) -> CleanReport:
        """Clean via the single removal path. Trash items require permanent."""
        if not permanent:
            blocked = [i for i in items if i.target_id == "trash"]
            if blocked:
                self._reporter.warn(
                    "Trash items can only be removed permanently "
                    f"(skipping {len(blocked)} items)."
                )
                items = [i for i in items if i.target_id != "trash"]
        remover = self._permanent_remover if permanent else self._trash_remover
        use_case = CleanUseCase(self._fs, remover, self._policy, self._reporter)
        targets = {t.id: t for t in self._all_targets}
        return use_case.execute(items, targets, dry_run=dry_run)
