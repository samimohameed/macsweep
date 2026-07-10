"""Safety tests.

These verify the core guarantee: no code path can remove system files,
applications, or user data — even with hostile inputs (symlink escapes,
misconfigured items, paths outside targets).

Run:  python3 -m pytest tests/ -v      (or python3 tests/test_safety.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maccleaner.application.clean import CleanUseCase
from maccleaner.application.scan import ScanUseCase
from maccleaner.domain.entities import CleanupItem, CleanupTarget
from maccleaner.domain.policies import SafetyPolicy
from maccleaner.infrastructure.fs_adapter import LocalFileSystem

HOME = Path.home()
POLICY = SafetyPolicy()


def _home_tmpdir() -> tempfile.TemporaryDirectory:
    """Temp dir under $HOME instead of the default /var/folders/…

    The system temp location resolves to /private/var/…, which the
    SafetyPolicy blocklist protects — so tests that expect a *successful*
    removal must run somewhere the policy actually allows.
    """
    return tempfile.TemporaryDirectory(dir=str(HOME), prefix=".maccleaner-test-")


class TestSafetyPolicy(unittest.TestCase):
    def test_rejects_system_paths(self):
        for p in [
            Path("/System/Library/CoreServices"),
            Path("/Library/Extensions"),
            Path("/usr/bin/python3"),
            Path("/bin/ls"),
            Path("/etc/hosts"),
            Path("/var/db"),
            Path("/private/var/folders/xx"),
        ]:
            self.assertIsNotNone(POLICY.validate(p, Path("/")), p)

    def test_rejects_applications(self):
        self.assertIsNotNone(
            POLICY.validate(Path("/Applications/Safari.app"), Path("/Applications"))
        )
        self.assertIsNotNone(
            POLICY.validate(HOME / "Applications" / "X.app", HOME / "Applications")
        )

    def test_rejects_user_data(self):
        for p in [
            HOME / "Documents" / "thesis.docx",
            HOME / "Desktop" / "notes.txt",
            HOME / "Downloads" / "installer.dmg",
            HOME / "Pictures" / "family.jpg",
            HOME / "Library" / "Application Support" / "App" / "data.db",
            HOME / "Library" / "Preferences" / "com.app.plist",
            HOME / "Library" / "Keychains" / "login.keychain-db",
            HOME / "Library" / "Mobile Documents" / "doc.pages",
        ]:
            # Even if such a path were somehow "inside" a target root,
            # the blocklist must reject it.
            self.assertIsNotNone(POLICY.validate(p, HOME), p)

    def test_rejects_root_and_home(self):
        self.assertIsNotNone(POLICY.validate(Path("/"), Path("/")))
        self.assertIsNotNone(POLICY.validate(HOME, HOME))

    def test_rejects_escape_from_target_root(self):
        root = HOME / "Library" / "Caches"
        outside = HOME / "Documents" / "file.txt"
        reason = POLICY.validate(outside, root)
        self.assertIsNotNone(reason)

    def test_rejects_target_root_itself(self):
        root = HOME / "Library" / "Caches"
        self.assertIsNotNone(POLICY.validate(root, root))

    def test_accepts_cache_content(self):
        root = HOME / "Library" / "Caches"
        self.assertIsNone(POLICY.validate(root / "com.example.app", root))

    def test_age_gate(self):
        self.assertIsNotNone(POLICY.validate_age(2.0, 7))
        self.assertIsNone(POLICY.validate_age(8.0, 7))


class TestSymlinkEscape(unittest.TestCase):
    """A cache entry that is a symlink pointing at real user data must
    never be followed and removed."""

    def test_scan_skips_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_cache = tmp_path / "Caches"
            fake_docs = tmp_path / "Documents"
            fake_cache.mkdir()
            fake_docs.mkdir()
            precious = fake_docs / "precious.txt"
            precious.write_text("do not delete")
            link = fake_cache / "evil-link"
            link.symlink_to(fake_docs)

            old = time.time() - 30 * 86_400
            os.utime(precious, (old, old))
            os.utime(link, (old, old), follow_symlinks=False)

            target = CleanupTarget(
                id="t", name="t", description="", root=fake_cache, min_age_days=1
            )
            report = ScanUseCase(LocalFileSystem(), POLICY).execute([target])

            scanned_paths = [i.path for i in report.items]
            self.assertNotIn(fake_docs, scanned_paths)
            self.assertTrue(
                any("escape" in reason for _p, reason in report.skipped),
                f"expected symlink escape to be skipped: {report.skipped}",
            )
            self.assertTrue(precious.exists())


class RecordingRemover:
    def __init__(self):
        self.removed: list[Path] = []

    def remove(self, path: Path) -> None:
        self.removed.append(path)


class NullReporter:
    def info(self, m): ...
    def warn(self, m): ...


class TestCleanUseCase(unittest.TestCase):
    def test_dry_run_never_calls_remover(self):
        with _home_tmpdir() as tmp:
            root = Path(tmp) / "Caches"
            root.mkdir()
            victim = root / "cache-entry"
            victim.write_text("x" * 100)
            old = time.time() - 30 * 86_400
            os.utime(victim, (old, old))

            target = CleanupTarget(
                id="t", name="t", description="", root=root, min_age_days=1
            )
            item = CleanupItem("t", victim, 100, 30.0)
            remover = RecordingRemover()
            result = CleanUseCase(
                LocalFileSystem(), remover, POLICY, NullReporter()
            ).execute([item], {"t": target}, dry_run=True)

            self.assertEqual(remover.removed, [])
            self.assertEqual(len(result.removed), 1)
            self.assertTrue(victim.exists())

    def test_clean_revalidates_and_blocks_hostile_item(self):
        """An item pointing at user data must be blocked at clean time,
        even if it somehow made it into the item list."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Caches"
            root.mkdir()
            target = CleanupTarget(
                id="t", name="t", description="", root=root, min_age_days=1
            )
            hostile = CleanupItem("t", HOME, 1, 999.0)  # home dir itself!
            remover = RecordingRemover()
            result = CleanUseCase(
                LocalFileSystem(), remover, POLICY, NullReporter()
            ).execute([hostile], {"t": target}, dry_run=False)

            self.assertEqual(remover.removed, [])
            self.assertEqual(len(result.failed), 1)

    def test_clean_blocks_unknown_target(self):
        item = CleanupItem("nonexistent", Path("/tmp/x"), 1, 99.0)
        remover = RecordingRemover()
        result = CleanUseCase(
            LocalFileSystem(), remover, POLICY, NullReporter()
        ).execute([item], {}, dry_run=False)
        self.assertEqual(remover.removed, [])
        self.assertEqual(len(result.failed), 1)

    def test_clean_blocks_too_recent_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Caches"
            root.mkdir()
            fresh = root / "fresh"
            fresh.write_text("new data")  # modified right now
            target = CleanupTarget(
                id="t", name="t", description="", root=root, min_age_days=7
            )
            item = CleanupItem("t", fresh, 8, 0.0)
            remover = RecordingRemover()
            result = CleanUseCase(
                LocalFileSystem(), remover, POLICY, NullReporter()
            ).execute([item], {"t": target}, dry_run=False)
            self.assertEqual(remover.removed, [])
            self.assertEqual(len(result.failed), 1)
            self.assertTrue(fresh.exists())

    def test_clean_removes_valid_old_cache_entry(self):
        with _home_tmpdir() as tmp:
            root = Path(tmp) / "Caches"
            root.mkdir()
            victim = root / "old-cache"
            victim.write_text("x" * 50)
            old = time.time() - 30 * 86_400
            os.utime(victim, (old, old))
            target = CleanupTarget(
                id="t", name="t", description="", root=root, min_age_days=1
            )
            item = CleanupItem("t", victim.resolve(), 50, 30.0)
            remover = RecordingRemover()
            result = CleanUseCase(
                LocalFileSystem(), remover, POLICY, NullReporter()
            ).execute([item], {"t": target}, dry_run=False)
            self.assertEqual(len(result.removed), 1)
            self.assertEqual(remover.removed, [victim.resolve()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
