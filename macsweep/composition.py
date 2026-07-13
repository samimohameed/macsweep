"""Composition root shared by all presentation layers.

The only module (besides tests) that wires concrete infrastructure to
the application layer. CLI and GUI both call build_app() and stay free
of adapter imports.
"""
from __future__ import annotations

from .application.app_service import AppService
from .application.ports import ReporterPort
from .domain.policies import SafetyPolicy
from .infrastructure.fs_adapter import LocalFileSystem
from .infrastructure.macos_insights import default_insights
from .infrastructure.macos_targets import default_targets
from .infrastructure.trash import PermanentRemover, TrashRemover


def build_app(reporter: ReporterPort) -> AppService:
    return AppService(
        fs=LocalFileSystem(),
        policy=SafetyPolicy(),
        reporter=reporter,
        all_targets=default_targets(),
        trash_remover=TrashRemover(),
        permanent_remover=PermanentRemover(),
        insight_specs=default_insights(),
    )
