"""CLI presentation layer.

All wiring lives in macsweep/composition.py; all selection/scan/clean
logic lives in the AppService facade. This module only parses arguments
and formats output.

Usage:
    python3 -m macsweep scan
    python3 -m macsweep scan --include trash
    python3 -m macsweep clean                # dry run (default!)
    python3 -m macsweep clean --yes          # actually move to Trash
    python3 -m macsweep clean --include trash --permanent --yes
    python3 -m macsweep gui                  # desktop app (needs PySide6)
"""
from __future__ import annotations

import argparse
import platform
import sys

from ..composition import build_app
from ..domain.entities import Risk


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


class ConsoleReporter:
    def info(self, message: str) -> None:
        print(message)

    def warn(self, message: str) -> None:
        print(f"⚠️  {message}", file=sys.stderr)


def _print_report(report, names: dict[str, str], verbose: bool) -> None:
    grouped = report.by_target()
    if not grouped:
        print("Nothing eligible for cleanup was found. Your Mac looks tidy.")
    for target_id, items in sorted(
        grouped.items(), key=lambda kv: -sum(i.size_bytes for i in kv[1])
    ):
        subtotal = sum(i.size_bytes for i in items)
        print(f"\n{names.get(target_id, target_id)}  —  {_human(subtotal)} "
              f"({len(items)} items)")
        for item in sorted(items, key=lambda i: -i.size_bytes)[:10]:
            print(f"   {_human(item.size_bytes):>10}  {item.path}")
        if len(items) > 10:
            print(f"   … and {len(items) - 10} more")
    print(f"\nTotal reclaimable: {_human(report.total_bytes)}")
    if verbose and report.skipped:
        print(f"\nSkipped ({len(report.skipped)}):")
        for path, reason in report.skipped:
            print(f"   {path}  ->  {reason}")
    if report.errors:
        print(f"\nErrors ({len(report.errors)}):")
        for path, reason in report.errors[:20]:
            print(f"   {path}  ->  {reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="macsweep",
        description="Safe, whitelist-only storage cleaner for macOS. "
                    "Never touches system files, applications, or user data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("targets", help="List all cleanup targets")
    sub.add_parser("insights", help="Show big tool-managed stores MacSweep "
                                    "won't touch, and the safe way to reclaim them")
    sub.add_parser("gui", help="Launch the desktop app (requires PySide6)")

    p_scan = sub.add_parser("scan", help="Scan (read-only) and show reclaimable space")
    p_clean = sub.add_parser("clean", help="Clean scanned items (dry run by default)")

    for p in (p_scan, p_clean):
        p.add_argument(
            "--include", action="append", default=[], metavar="TARGET_ID",
            help="Include an opt-in target such as 'trash' (repeatable)",
        )
        p.add_argument("--only", action="append", default=[], metavar="TARGET_ID",
                       help="Restrict to specific target ids (repeatable)")
        p.add_argument("--min-age", type=int, default=None, metavar="DAYS",
                       help="Override minimum age in days (raise only)")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="Show skipped items and reasons")

    p_clean.add_argument("--yes", action="store_true",
                         help="Actually perform the clean (otherwise dry run)")
    p_clean.add_argument("--permanent", action="store_true",
                         help="Delete permanently instead of moving to Trash "
                              "(required for the 'trash' target)")

    args = parser.parse_args(argv)

    if platform.system() != "Darwin":
        print("This tool is designed for macOS.", file=sys.stderr)

    if args.command == "gui":
        from .gui.app import run_gui  # lazy: PySide6 is an optional dependency
        return run_gui()

    app = build_app(ConsoleReporter())

    if args.command == "targets":
        for t in app.list_targets():
            flag = " (opt-in)" if t.risk is Risk.OPT_IN else ""
            print(f"{t.id:<22} {t.name}{flag}\n{'':<22} {t.description}\n")
        return 0

    if args.command == "insights":
        insights = app.insights()
        if not insights:
            print("No large tool-managed stores found. Nothing to point at.")
            return 0
        print("Big stores MacSweep deliberately won't touch — and the safe "
              "way to reclaim them:\n")
        for ins in insights:
            print(f"  {ins.title}  —  {_human(ins.size_bytes)}")
            print(f"     {ins.path}")
            print(f"     {ins.explanation}")
            verb = "Run:" if ins.copyable else "Do: "
            print(f"     {verb} {ins.command}\n")
        return 0

    targets = app.select_targets(
        include_opt_in=args.include, only=args.only, min_age_days=args.min_age
    )
    report = app.scan(targets)
    names = {t.id: t.name for t in app.list_targets()}
    _print_report(report, names, args.verbose)

    if args.command == "scan":
        return 0

    # ---- clean ----
    dry_run = not args.yes
    if dry_run:
        print("\nDRY RUN — nothing was removed. Re-run with --yes to clean.")

    if not dry_run and args.permanent:
        answer = input(
            "⚠️  --permanent deletes items irreversibly (no Trash recovery).\n"
            "Type 'DELETE' to confirm: "
        )
        if answer.strip() != "DELETE":
            print("Aborted.")
            return 1

    result = app.clean(report.items, dry_run=dry_run, permanent=args.permanent)

    verb = "Would free" if dry_run else "Freed"
    dest = "" if args.permanent else " (items moved to Trash — recoverable)"
    print(f"\n{verb}: {_human(result.freed_bytes)} "
          f"across {len(result.removed)} items{dest}")
    if result.failed:
        print(f"Failed/blocked: {len(result.failed)}")
        for item, reason in result.failed[:20]:
            print(f"   {item.path}  ->  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
