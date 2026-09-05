"""Preview server: Spectra CSS stub + live schedule JSON from a public Trakt profile."""

from __future__ import annotations

import importlib.util
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
STUB = ROOT / "preview" / "spectra-stub.css"
CACHE = ROOT / "preview" / ".cache"
CORE_PATH = ROOT / "trakt_core" / "server.py"

_core = None


def _load_core():
    global _core
    if _core is None:
        spec = importlib.util.spec_from_file_location("trakt_core_server", CORE_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _core = mod
    return _core


def live_payload(view: str, username: str, list_status: str) -> dict:
    core = _load_core()
    CACHE.mkdir(parents=True, exist_ok=True)
    return core.load_schedule(
        {
            "username": username,
            "list_status": list_status,
            "refresh_min": 20,
        },
        {"data_dir": str(CACHE / "trakt_core")},
        view=view,
    )


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path: str) -> str:
        if path.startswith("/static/style/spectra-widgets.css"):
            return str(STUB)
        return super().translate_path(path)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/preview/live.json", "/preview/live"}:
            qs = parse_qs(parsed.query)
            view = (qs.get("view") or ["agenda"])[0]
            if view not in {"agenda", "month", "releases"}:
                view = "agenda"
            username = (qs.get("username") or [os.environ.get("TRAKT_USERNAME") or "bestora"])[0]
            list_status = (qs.get("list") or ["watching"])[0]
            try:
                payload = live_payload(view, username, list_status)
                if view == "releases" and not payload.get("error"):
                    events = [
                        e for e in (payload.get("events") or [])
                        if e.get("state") in {"aired", "now"}
                    ]
                    events.sort(key=lambda e: e.get("airing_at") or 0, reverse=True)
                    payload["events"] = events[:12]
                    payload["aired"] = len(events)
            except Exception as err:
                payload = {"error": str(err)}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8767), Handler).serve_forever()
