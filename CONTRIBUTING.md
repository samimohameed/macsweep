# Contributing to MacCleaner

Thanks for helping! The easiest and most valuable contribution is **adding a new cleanup target** — see below.

## Ground rules (the safety model is non-negotiable)

MacCleaner's whole value is that it *cannot* damage a Mac. Every PR must preserve that:

1. **Never weaken `SafetyPolicy`** (`maccleaner/domain/policies.py`). The blocklist and symlink-escape checks apply on top of every target — including yours.
2. **All removal goes through `CleanUseCase`.** Do not add a second code path that deletes anything.
3. **Whitelist only.** No feature may walk arbitrary directories. New locations are added as `CleanupTarget` entries, nothing else.
4. **No `sudo`, ever.** User-scope locations only.
5. **Recoverable by default.** New features default to dry-run / move-to-Trash.
6. **Safety tests must pass** (`python3 -m pytest tests/ -v`) and new targets/features need tests.

## Adding a cleanup target (great first PR!)

1. Append a `CleanupTarget` to `default_targets()` in `maccleaner/infrastructure/macos_targets.py`:
   - `root` must be a user-scope absolute path (usually under `~/Library` or a tool's cache dir).
   - Pick a conservative `min_age_days` (7+ for caches, 30 for anything the user might miss).
   - Use `Risk.OPT_IN` if removal could surprise anyone.
   - Write a `description` that explains *why* it is safe to remove.
2. Run `python3 -m maccleaner scan --only your-target-id -v` and check the skipped/errors output.
3. Add a test if the target has any subtlety (globs, opt-in, unusual layout).

## Development setup

```bash
git clone https://github.com/<you>/mac-cleaner && cd mac-cleaner
python3 -m pip install -e '.[dev,gui]'
python3 -m pytest tests/ -v      # safety tests
python3 -m maccleaner scan       # read-only, always safe to run
python3 -m maccleaner gui        # desktop app
```

## Architecture

Clean Architecture — dependencies point inward only:

- `domain/` — entities + `SafetyPolicy`. Pure Python, imports nothing outside itself.
- `application/` — use cases and the `AppService` facade. Depends only on domain + ports.
- `infrastructure/` — adapters implementing the ports, plus the target whitelist.
- `presentation/` — CLI and PySide6 GUI. UI only; no business logic.
- `composition.py` — the single place where adapters are wired to use cases.

If you're unsure where something belongs: logic about *what is safe* goes in domain, *how a feature works* in application, *how macOS is touched* in infrastructure, and *how it looks* in presentation.

## Pull requests

- Keep PRs focused (one feature/target per PR).
- Explain how you verified the change (paste a `scan -v` snippet for new targets).
- CI runs the safety tests on macOS; a red build won't be merged.
