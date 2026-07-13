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
    Insight,
    Risk,
    ScanReport,
)
from ..domain.policies import SafetyPolicy
from .clean import CleanUseCase
from .ports import FileSystemPort, RemoverPort, ReporterPort
from .scan import ScanUseCase, resolve_roots


class AppService:
    def __init__(
        self,
        fs: FileSystemPort,
        policy: SafetyPolicy,
        reporter: ReporterPort,
        all_targets: list[CleanupTarget],
        trash_remover: RemoverPort,
        permanent_remover: RemoverPort,
        insight_specs: Optional[list[Insight]] = None,
    ) -> None:
        self._fs = fs
        self._policy = policy
        self._reporter = reporter
        self._all_targets = list(all_targets)
        self._trash_remover = trash_remover
        self._permanent_remover = permanent_remover
        self._insight_specs = list(insight_specs or [])

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
        # Scanning one target at a time (for progress) still needs the full
        # selection's roots so overlapping targets never claim an item twice.
        all_roots = resolve_roots(self._fs, targets)
        report = ScanReport()
        for target in targets:
            progress(target)
            partial = use_case.execute([target], exclude_roots=all_roots)
            report.items.extend(partial.items)
            report.skipped.extend(partial.skipped)
            report.errors.extend(partial.errors)
        return report

    def insights(self) -> list[Insight]:
        """Measure known tool-managed stores MacSweep refuses to touch.

        Read-only by construction: there is no code path from an Insight
        to any remover. Missing or unreadable locations are silently
        skipped; results are sorted largest first.
        """
        found: list[Insight] = []
        for spec in self._insight_specs:
            try:
                if not self._fs.exists(spec.path):
                    continue
                # Allocated (not apparent) size: sparse files like Docker's
                # disk image would otherwise overstate by hundreds of GB.
                size = self._fs.allocated_size_of(self._fs.resolve(spec.path))
            except OSError:
                continue
            if size >= spec.min_bytes:
                found.append(replace(spec, size_bytes=size))
        return sorted(found, key=lambda i: -i.size_bytes)

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
