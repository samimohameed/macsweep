# Changelog

## Unreleased

- **GUI: "Show skipped" view.** One click lists every item the scan saw but left alone, with the exact safety rule that protected it (age gate, blocklist, symlink escape…). Answers "why do different cleaners show different numbers?" with full transparency.
- **Four new cleanup targets**: Gradle cache (`~/.gradle/caches`), Cargo registry cache (`~/.cargo/registry/cache`), Go build cache (`~/Library/Caches/go-build`), and Playwright browser downloads (`~/Library/Caches/ms-playwright`, opt-out-friendly MODERATE risk). As always, the blocklist and age gate apply on top.
- **Redesigned app shell**: sidebar navigation (Cleanup / Insights) with the brand and safety promise always visible; page titles and a calmer, less busy layout.
- **Insights** (sidebar page + `macsweep insights` CLI): detects big tool-managed stores MacSweep deliberately won't touch — Docker data, iOS Simulators, device backups, the Trash — and shows the owning tool's own safe reclaim command (with one-click copy). Read-only by construction: insights have no code path to any remover. Sizes are measured in *allocated* disk blocks, so sparse files like Docker's disk image report real usage, not inflated apparent size.

## v0.2.2 — 2026-07-11

- **Fix: file ages are now honest for downloaded files.** Downloaders like Homebrew's preserve the *server's* modification time, so a bottle fetched an hour ago could show as "304 days old" and be swept by mistake. Age now also considers ctime (last change on this disk, which cannot be backdated), so freshly arrived files are correctly age-gated.
- Broken symlinks and files that vanish mid-scan are quietly skipped instead of reported as errors.

## v0.2.1 — 2026-07-11

- **Fix: scan totals no longer double-count.** Overlapping targets (e.g. the Homebrew cache living inside ~/Library/Caches) and symlink aliases within a cache (Homebrew's top-level links into downloads/) could count the same file twice and list it twice in the results. Each item is now claimed exactly once.
- **GUI visual refresh**: branded header with app icon and live reclaimable total, proportional per-category size bars, modern buttons and layout, `~`-shortened paths with full-path tooltips, alternating row colors, light/dark aware styling.
- App icon (window icon; `.icns` in `docs/` for future app bundles).

## v0.2.0 — 2026-07-10

First public release.

- **Desktop app** (PySide6): scan dashboard with per-category checkboxes, live selection totals, background scanning/cleaning, per-item progress. Only ever moves items to the Trash.
- **Deep scan**: the scanner descends into recently-used cache folders and collects the old content inside them — typically unlocking gigabytes that a naive age check would skip.
- **CLI**: `macsweep targets | scan | clean` with dry-run by default, `--include trash`, `--min-age` (raise only), `--permanent` (double-confirmed).
- **Safety model**: whitelist-only targets, independent blocklist, symlink-escape protection, age gate, removal-time re-validation, no sudo ever. 15 safety tests, run in CI on macOS.
- Adaptive Trash strategy: native Finder trashing (keeps "Put Back") within a time budget, then fast direct moves for large batches.
