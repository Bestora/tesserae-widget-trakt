"""Smoke: the widget folders load a render module."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_plugin_manifests_exist():
    for name in ("trakt_core", "trakt_schedule", "trakt_month", "trakt_releases"):
        assert (ROOT / name / "plugin.json").is_file()
    for name in ("trakt_schedule", "trakt_month", "trakt_releases"):
        assert (ROOT / name / "client.js").is_file()
        assert (ROOT / name / "server.py").is_file()
