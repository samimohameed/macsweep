"""Tests for the CLI presentation layer's --json output.

Presentation-layer only: exercises macsweep.presentation.cli.main() directly
against a stubbed AppService via build_app, rather than touching the real
filesystem or macOS targets.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from macsweep.domain.entities import CleanupItem, ScanReport
from macsweep.presentation.cli import main


def _fake_report() -> ScanReport:
    return ScanReport(
        items=[
            CleanupItem(
                target_id="user-caches",
                path=Path("/Users/demo/Library/Caches/example/blob"),
                size_bytes=4096,
                age_days=12.5,
            ),
            CleanupItem(
                target_id="user-logs",
                path=Path("/Users/demo/Library/Logs/example.log"),
                size_bytes=2048,
                age_days=30.0,
            ),
        ],
        skipped=[(Path("/Users/demo/Library/Caches/locked"), "in use")],
        errors=[],
    )


def _stub_app(report: ScanReport) -> MagicMock:
    app = MagicMock()
    app.select_targets.return_value = []
    app.scan.return_value = report
    app.list_targets.return_value = []
    return app


def test_scan_json_prints_only_valid_json_on_stdout(capsys):
    report = _fake_report()
    with patch("macsweep.presentation.cli.build_app", return_value=_stub_app(report)):
        exit_code = main(["scan", "--json"])

    assert exit_code == 0
    captured = capsys.readouterr()

    # stdout must be nothing but the JSON payload -- a scripting consumer
    # pipes this straight into a JSON parser (e.g. `macsweep scan --json | jq`).
    payload = json.loads(captured.out)

    assert payload["items"] == [
        {
            "path": str(Path("/Users/demo/Library/Caches/example/blob")),
            "target_id": "user-caches",
            "size_bytes": 4096,
            "age_days": 12.5,
        },
        {
            "path": str(Path("/Users/demo/Library/Logs/example.log")),
            "target_id": "user-logs",
            "size_bytes": 2048,
            "age_days": 30.0,
        },
    ]
    assert payload["total_bytes"] == 6144
    assert payload["skipped"] == 1
    assert payload["errors"] == 0


def test_scan_json_omits_text_report_formatting(capsys):
    report = _fake_report()
    with patch("macsweep.presentation.cli.build_app", return_value=_stub_app(report)):
        main(["scan", "--json"])

    captured = capsys.readouterr()

    # None of the human-readable report's strings should leak into --json
    # output -- confirms _print_report was skipped entirely, not just that
    # extra JSON was appended after it.
    assert "Total reclaimable" not in captured.out
    assert "items)" not in captured.out


def test_scan_without_json_still_prints_text_report(capsys):
    report = _fake_report()
    with patch("macsweep.presentation.cli.build_app", return_value=_stub_app(report)):
        exit_code = main(["scan"])

    assert exit_code == 0
    captured = capsys.readouterr()

    assert "Total reclaimable" in captured.out
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)


def test_scan_json_reports_empty_report_correctly(capsys):
    empty_report = ScanReport(items=[], skipped=[], errors=[])
    with patch(
        "macsweep.presentation.cli.build_app", return_value=_stub_app(empty_report)
    ):
        exit_code = main(["scan", "--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload == {
        "items": [],
        "total_bytes": 0,
        "skipped": 0,
        "errors": 0,
    }