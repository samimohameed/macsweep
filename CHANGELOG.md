# Changelog

## v0.2.0 — 2026-07-10

First public release.

- **Desktop app** (PySide6): scan dashboard with per-category checkboxes, live selection totals, background scanning/cleaning, per-item progress. Only ever moves items to the Trash.
- **Deep scan**: the scanner descends into recently-used cache folders and collects the old content inside them — typically unlocking gigabytes that a naive age check would skip.
- **CLI**: `macsweep targets | scan | clean` with dry-run by default, `--include trash`, `--min-age` (raise only), `--permanent` (double-confirmed).
- **Safety model**: whitelist-only targets, independent blocklist, symlink-escape protection, age gate, removal-time re-validation, no sudo ever. 15 safety tests, run in CI on macOS.
- Adaptive Trash strategy: native Finder trashing (keeps "Put Back") within a time budget, then fast direct moves for large batches.
