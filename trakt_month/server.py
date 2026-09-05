"""trakt_month — month grid of episode air dates."""

from __future__ import annotations

from typing import Any


def _core():
    from flask import current_app

    plugin = (current_app.config.get("PLUGIN_REGISTRY") or {}).get("trakt_core")
    if plugin is None or plugin.server_module is None:
        return None
    return plugin.server_module


def fetch(options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]) -> dict[str, Any]:
    del settings
    core = _core()
    if core is None:
        return {"error": "Install the Trakt bundle — trakt_core is missing."}
    try:
        return core.load_schedule(options, ctx, view="month")
    except Exception:
        return {"error": "Couldn't load the Trakt calendar right now."}
