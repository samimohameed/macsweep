# Launch post drafts

Post one channel at a time, a few days apart. Reply to every comment quickly —
early responsiveness is what turns a post into stars and contributors.

---

## r/macapps (also adaptable for r/MacOS)

**Title:** I built a free, open-source CleanMyMac alternative that architecturally can't delete your files

**Body:**

I got tired of paying for cleaner apps I couldn't audit, so I built MacSweep: a free, MIT-licensed storage cleaner for macOS.

The design goal was different from other cleaners: instead of promising to be careful, it's built so it *can't* be dangerous:

- **Whitelist-only.** It can only scan a hardcoded registry of known-safe locations (app caches, logs, npm/pip/Homebrew caches, Xcode DerivedData). There is no code path that walks arbitrary folders.
- **Independent blocklist on top.** Every path is re-checked against protected locations (/System, /Applications, Documents, Photos, iCloud Drive…) — even a misconfigured entry can't reach them.
- **Everything goes to the Trash.** Nothing is permanently deleted unless you explicitly ask twice.
- **Never asks for admin rights.** If a cleaner needs sudo, it can hurt you. This one refuses to run with it.
- The safety rules are unit-tested and run in CI on every change.

It found ~1.4 GB on my machine on first scan. Desktop app (screenshot in the repo) + CLI.

GitHub: https://github.com/samimohameed/macsweep

It's early days — if your favorite tool's cache isn't covered, adding a target is a ~15-line PR and there are "good first issue" tickets waiting.

---

## Show HN

**Title:** Show HN: MacSweep – open-source Mac cleaner that can't touch your files by design

**Body:**

Commercial Mac cleaners ask you to trust them with root access to your disk. I wanted the opposite: a cleaner whose safety you can verify by reading the code.

The core idea is defense in depth, enforced by architecture (Clean Architecture — the safety rules are pure-Python domain code with zero dependencies, so they're trivially testable):

1. Whitelist-only scanning — locations enter the system only through a hardcoded target registry
2. An independent blocklist re-validates every path (so even a bad registry entry can't reach /System or ~/Documents)
3. Symlink-escape protection — resolved paths must stay inside their target root
4. An age gate — recently-modified items are never touched (with depth-limited recursion into active cache dirs, since that's where the reclaimable gigabytes actually live)
5. Everything is re-validated a second time at removal, in the single code path that can remove anything
6. Items go to the Trash, not oblivion; no sudo, ever

Python 3.9+ stdlib only for the core; optional PySide6 GUI. I'd genuinely welcome attempts to construct a hostile input (symlink chains, TOCTOU races) that gets past the policy — that's what the test suite tries to do.

https://github.com/samimohameed/macsweep

---

## X / Mastodon

Cleaned 1.4 GB off my Mac with a cleaner I can actually audit.

I built MacSweep: free, open-source, whitelist-only — it architecturally *cannot* touch system files or your documents. Everything goes to the Trash. Never needs sudo.

⭐ https://github.com/samimohameed/macsweep
