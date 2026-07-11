"""Scan use case.

Read-only. Walks registered targets, applies the SafetyPolicy and age
gate to every candidate, and produces a ScanReport. Nothing is removed
here under any circumstances.

A directory that fails the age gate (something inside was modified
recently) is not discarded outright: the scanner descends into it —
depth-limited — and collects the entries that individually pass the
gate. Actively-used caches usually hold mostly old content, and this is
where the bulk of reclaimable space lives.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..domain.entities import CleanupItem, CleanupTarget, ScanReport
from ..domain.policies import SafetyPolicy
from .ports import FileSystemPort

# How deep to descend into age-gated directories looking for old content.
# 6 levels reaches nested layouts like npm's _cacache/content-v2/sha512/xx/yy
# and browser cache shards; beyond that returns are negligible.
MAX_RECURSE_DEPTH = 6


def _dedupe(items: list[CleanupItem]) -> list[CleanupItem]:
    """Drop items whose resolved path was already claimed, exactly or by an
    ancestor directory. Happens when a cache holds symlink aliases to its
    own content (e.g. Homebrew's top-level links into downloads/): both the
    alias and the real file resolve to the same path, or a file is claimed
    individually and then again as part of its parent directory.
    """
    result: list[CleanupItem] = []
    claimed: set[str] = set()
    # Sorting puts a directory before anything inside it, so ancestors are
    # always claimed before their descendants are considered.
    for item in sorted(items, key=lambda i: str(i.path)):
        path = str(item.path)
        if path in claimed or any(str(p) in claimed for p in item.path.parents):
            continue
        result.append(item)
        claimed.add(path)
    return result


def resolve_roots(fs: FileSystemPort, targets: list[CleanupTarget]) -> set[Path]:
    """Resolved roots of the given targets (missing/broken roots skipped)."""
    roots: set[Path] = set()
    for target in targets:
        try:
            if fs.exists(target.root):
                roots.add(fs.resolve(target.root))
        except OSError:
            continue
    return roots


class ScanUseCase:
    def __init__(self, fs: FileSystemPort, policy: SafetyPolicy) -> None:
        self._fs = fs
        self._policy = policy

    def execute(
        self,
        targets: list[CleanupTarget],
        exclude_roots: Optional[set[Path]] = None,
    ) -> ScanReport:
        """Scan targets.

        `exclude_roots` are the resolved roots of every *selected* target;
        a broader target skips them so an item is never claimed twice
        (e.g. ~/Library/Caches/Homebrew is scanned only by the homebrew
        target, never also by user-caches). Defaults to the roots of
        `targets` itself; callers that scan targets one at a time must
        pass the full selection's roots (see AppService.scan).
        """
        report = ScanReport()
        if exclude_roots is None:
            exclude_roots = resolve_roots(self._fs, targets)

        for target in targets:
            if not self._fs.exists(target.root):
                continue  # target simply not present on this machine

            try:
                resolved_root = self._fs.resolve(target.root)
            except OSError as exc:
                report.errors.append((target.root, str(exc)))
                continue

            others = exclude_roots - {resolved_root}
            self._scan_dir(target, resolved_root, target.root, 0, report, others)

        report.items = _dedupe(report.items)
        return report

    def _scan_dir(
        self,
        target: CleanupTarget,
        resolved_root: Path,
        directory: Path,
        depth: int,
        report: ScanReport,
        exclude_roots: set[Path],
    ) -> None:
        # The target's glob selects top-level candidates; deeper levels
        # consider everything (still guarded by policy + age gate).
        glob = target.glob if depth == 0 else "*"
        for child in self._fs.iter_children(directory, glob):
            try:
                resolved = self._fs.resolve(child)

                if resolved in exclude_roots:
                    continue  # owned by a more specific target

                reason = self._policy.validate(resolved, resolved_root)
                if reason:
                    report.skipped.append((child, reason))
                    continue

                age = self._fs.age_days(resolved)
                reason = self._policy.validate_age(age, target.min_age_days)
                if reason:
                    if depth < MAX_RECURSE_DEPTH and self._fs.is_dir(resolved):
                        # Recently-touched directory: look inside for old
                        # entries instead of writing the whole thing off.
                        self._scan_dir(
                            target, resolved_root, resolved, depth + 1,
                            report, exclude_roots,
                        )
                    else:
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
