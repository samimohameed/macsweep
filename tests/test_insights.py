"""Insights tests.

Insights are read-only pointers at big tool-managed stores. These tests
verify the size gate, sorting, graceful handling of missing paths — and
that the feature has no path to any remover.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macsweep.application.app_service import AppService
from macsweep.domain.entities import Insight
from macsweep.domain.policies import SafetyPolicy
from macsweep.infrastructure.fs_adapter import LocalFileSystem


class ExplodingRemover:
    """Any removal attempt during insights is a test failure."""

    def remove(self, path):
        raise AssertionError(f"insights must never remove anything: {path}")


class NullReporter:
    def info(self, m): ...
    def warn(self, m): ...


def _service(specs):
    return AppService(
        fs=LocalFileSystem(),
        policy=SafetyPolicy(),
        reporter=NullReporter(),
        all_targets=[],
        trash_remover=ExplodingRemover(),
        permanent_remover=ExplodingRemover(),
        insight_specs=specs,
    )


def _spec(id_, path, min_bytes):
    return Insight(
        id=id_, title=id_, path=path, explanation="", command="true",
        min_bytes=min_bytes,
    )


class TestInsights(unittest.TestCase):
    def test_size_gate_sorting_and_missing_paths(self):
        # Sizes are measured in allocated blocks (4 KB granularity), so
        # fixture sizes must be far apart, not byte-exact.
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big"
            big.mkdir()
            (big / "blob").write_bytes(b"x" * 50_000)
            small = Path(tmp) / "small"
            small.mkdir()
            (small / "blob").write_bytes(b"x" * 10)       # 1 block
            medium = Path(tmp) / "medium"
            medium.mkdir()
            (medium / "blob").write_bytes(b"x" * 20_000)

            service = _service([
                _spec("small", small, min_bytes=10_000),   # below gate
                _spec("medium", medium, min_bytes=10_000),
                _spec("big", big, min_bytes=10_000),
                _spec("missing", Path(tmp) / "nope", min_bytes=0),
            ])
            found = service.insights()

            self.assertEqual([i.id for i in found], ["big", "medium"])
            self.assertGreaterEqual(found[0].size_bytes, 50_000)

    def test_no_insights_configured(self):
        self.assertEqual(_service([]).insights(), [])

    def test_sparse_files_report_allocated_not_apparent_size(self):
        """Docker's disk image is sparse: apparent size can be 100s of GB
        while using almost no disk. Insights must not inflate."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "docker-like"
            store.mkdir()
            sparse = store / "Docker.raw"
            with open(sparse, "wb") as f:
                f.seek(50 * 1024 * 1024 - 1)  # 50 MB apparent
                f.write(b"\0")                # ~1 block allocated

            service = _service([_spec("docker", store, min_bytes=1024 * 1024)])
            found = service.insights()
            # ~4KB allocated is far below the 1 MB gate -> hidden.
            self.assertEqual(found, [], f"sparse file inflated: {found}")


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=1))
