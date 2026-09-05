"""trakt_releases — recently aired episodes from a Trakt list."""

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
        payload = core.load_schedule(options, ctx, view="releases")
    except Exception:
        return {"error": "Couldn't load recent Trakt releases right now."}
    if payload.get("error"):
        return payload
    events = [e for e in (payload.get("events") or []) if e.get("state") in {"aired", "now"}]
    events.sort(key=lambda e: e.get("airing_at") or 0, reverse=True)
    try:
        cap = max(1, int(options.get("max_items") or 12))
    except (TypeError, ValueError):
        cap = 12
    payload["events"] = events[:cap]
    payload["aired"] = len(events)
    return payload
