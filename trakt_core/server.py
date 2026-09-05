"""Shared Trakt list fetch + episode air calendar.

Sibling trakt_* widgets call ``load_schedule`` via the plugin registry.
A Client ID is required (Trakt's public API still wants ``trakt-api-key``).
Public profiles are read without OAuth: watched / watchlist / collection,
then the global show calendar is filtered to those ids.
"""

from __future__ import annotations

import calendar
import contextlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TRAKT_API = "https://api.trakt.tv"
USER_AGENT = "tesserae/0.1 (+trakt_core)"
HTTP_TIMEOUT_S = 8
CACHE_TTL_S = 20 * 60
MAX_LIST_PAGES = 20
PAGE_LIMIT = 100
CALENDAR_MAX_DAYS = 33

LIST_STATUSES = ("watching", "watchlist", "collection", "all")
LIST_LABELS = {
    "watching": "Watching",
    "watchlist": "Watchlist",
    "collection": "Collection",
    "all": "All",
}

_USER_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|app\.)?trakt\.tv/(?:users|profile)/([A-Za-z0-9_-]+)",
    re.I,
)
_USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

ERR_NO_CLIENT = (
    "Add a Trakt Client ID under Settings → Plugins → Trakt Core. "
    "Create an app at trakt.tv/oauth/applications — only the Client ID is needed."
)
ERR_NO_USER = "Set a Trakt username on this cell, or a default in Trakt Core settings."
ERR_BAD_USER = "That doesn't look like a Trakt username."
ERR_NOT_FOUND = "Trakt user '{user}' was not found. Check the spelling and that the profile is public."
ERR_BAD_CLIENT = "Trakt rejected the Client ID. Create a new one at trakt.tv/oauth/applications."
ERR_PRIVATE = "Trakt user '{user}' has a private profile."
ERR_RATE = "Trakt rate-limited the request. Try again in a few minutes."
ERR_UPSTREAM = "Couldn't load Trakt right now."


def _core_settings() -> dict[str, Any]:
    try:
        from flask import current_app, has_app_context

        if not has_app_context():
            return {}
        store = current_app.config.get("SETTINGS_STORE")
        if store is None:
            return {}
        plugins = {}
        with contextlib.suppress(Exception):
            plugins = store.get_section("plugins") or {}
        if isinstance(plugins, dict) and isinstance(plugins.get("trakt_core"), dict):
            return plugins["trakt_core"]
        with contextlib.suppress(Exception):
            direct = store.get_section("trakt_core")
            if isinstance(direct, dict):
                return direct
    except Exception:
        return {}
    return {}


def get_client_id() -> str:
    s = _core_settings()
    cid = (s.get("client_id_secret") or s.get("client_id") or "").strip()
    if cid:
        return cid
    return (os.environ.get("TRAKT_CLIENT_ID") or "").strip()


def get_default_username() -> str:
    return parse_username(_core_settings().get("username") or "")


def parse_username(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    m = _USER_URL_RE.search(text)
    if m:
        return m.group(1)
    if text.startswith("@"):
        text = text[1:]
    return text if _USER_RE.match(text) else ""


def list_status_of(raw: str) -> str:
    value = (raw or "watching").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "watched": "watching",
        "progress": "watching",
        "plan_to_watch": "watchlist",
        "plantowatch": "watchlist",
        "ptw": "watchlist",
        "collected": "collection",
    }
    value = aliases.get(value, value)
    return value if value in LIST_STATUSES else "watching"


def _timezone() -> Any:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            with contextlib.suppress(Exception):
                from app.tz_resolve import app_timezone

                return app_timezone()
            with contextlib.suppress(Exception):
                from app.timezone import app_timezone

                return app_timezone()
            store = current_app.config.get("SETTINGS_STORE")
            if store is not None:
                app_s = store.get_section("app") or {}
                name = str(app_s.get("timezone") or "").strip()
                if name and name not in {"system", ""}:
                    return ZoneInfo(name)
    except Exception:
        pass
    tz = datetime.now().astimezone().tzinfo
    return tz or UTC


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_air(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    with contextlib.suppress(ValueError):
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    return None


def last_watched_pair(item: dict[str, Any]) -> tuple[int, int]:
    """Highest (season, episode) the user has plays on. (0, 0) if none."""
    best = (0, 0)
    for season in item.get("seasons") or []:
        if not isinstance(season, dict):
            continue
        sn = _to_int(season.get("number")) or 0
        for ep in season.get("episodes") or []:
            if not isinstance(ep, dict):
                continue
            if not ep.get("plays"):
                continue
            pair = (sn, _to_int(ep.get("number")) or 0)
            if pair > best:
                best = pair
    return best


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = HTTP_TIMEOUT_S,
) -> tuple[Any, str | None, dict[str, str]]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            body = resp.read().decode("utf-8", "replace")
            if not body.strip():
                return [], None, hdrs
            return json.loads(body), None, hdrs
    except urllib.error.HTTPError as err:
        return None, _trakt_http_error(err), {}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, ERR_UPSTREAM, {}


def _trakt_http_error(err: urllib.error.HTTPError) -> str:
    snippet = ""
    with contextlib.suppress(Exception):
        snippet = err.read().decode("utf-8", "replace")[:800].lower()
    if err.code in (401, 403) and "invalid" in snippet and "trakt-api-key" in snippet:
        return ERR_BAD_CLIENT
    if err.code == 401:
        return ERR_BAD_CLIENT
    if err.code == 403 or "private" in snippet:
        return ERR_PRIVATE
    if err.code == 404:
        return ERR_NOT_FOUND
    if err.code == 429:
        return ERR_RATE
    return ERR_UPSTREAM


def _with_user(err: str | None, username: str) -> str | None:
    if not err:
        return None
    if "{user}" in err:
        return err.format(user=username)
    return err


def trakt_headers(client_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
    }


def trakt_get(
    path: str,
    client_id: str,
    params: dict[str, Any] | None = None,
) -> tuple[Any, str | None, dict[str, str]]:
    query = urllib.parse.urlencode(
        {k: v for k, v in (params or {}).items() if v not in (None, "")}
    )
    url = f"{TRAKT_API}{path}"
    if query:
        url = f"{url}?{query}"
    return _http_json(url, headers=trakt_headers(client_id))


def trakt_get_pages(path: str, client_id: str) -> tuple[list[Any] | None, str | None]:
    out: list[Any] = []
    page = 1
    while page <= MAX_LIST_PAGES:
        payload, err, hdrs = trakt_get(
            path, client_id, {"page": page, "limit": PAGE_LIMIT}
        )
        if err:
            return None, err
        if not isinstance(payload, list):
            return None, ERR_UPSTREAM
        out.extend(payload)
        try:
            page_count = int(hdrs.get("x-pagination-page-count") or 1)
        except ValueError:
            page_count = 1
        if page >= page_count or len(payload) < PAGE_LIMIT:
            break
        page += 1
    return out, None


def _show_blob(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    show = item.get("show")
    return show if isinstance(show, dict) else item


def show_trakt_id(item: dict[str, Any]) -> int | None:
    ids = _show_blob(item).get("ids") or {}
    if isinstance(ids, dict):
        return _to_int(ids.get("trakt"))
    return None


def show_title(item: dict[str, Any]) -> str:
    blob = _show_blob(item)
    return str(blob.get("title") or "").strip() or "Untitled"


def fetch_tracked(
    username: str, status: str, client_id: str
) -> tuple[dict[int, dict[str, Any]] | None, str | None]:
    """Map trakt show id → {title, last, list_status}."""
    paths: list[tuple[str, str]] = []
    quoted = urllib.parse.quote(username)
    if status in {"watching", "all"}:
        paths.append((f"/users/{quoted}/watched/shows", "watching"))
    if status in {"watchlist", "all"}:
        paths.append((f"/users/{quoted}/watchlist/shows", "watchlist"))
    if status in {"collection", "all"}:
        paths.append((f"/users/{quoted}/collection/shows", "collection"))
    if not paths:
        paths.append((f"/users/{quoted}/watched/shows", "watching"))

    tracked: dict[int, dict[str, Any]] = {}
    for path, label in paths:
        rows, err = trakt_get_pages(path, client_id)
        if err:
            return None, _with_user(err, username)
        for item in rows or []:
            if not isinstance(item, dict):
                continue
            sid = show_trakt_id(item)
            if sid is None:
                continue
            last = last_watched_pair(item) if label == "watching" else tracked.get(sid, {}).get("last", (0, 0))
            if sid in tracked and label != "watching":
                continue
            tracked[sid] = {
                "id": sid,
                "title": show_title(item),
                "last": last if label == "watching" else tracked.get(sid, {}).get("last", (0, 0)),
                "list_status": label,
            }
            if label == "watching":
                tracked[sid]["last"] = last
    return tracked, None


def fetch_calendar(
    client_id: str, start: datetime, end: datetime
) -> tuple[list[dict[str, Any]] | None, str | None]:
    items: list[dict[str, Any]] = []
    cursor = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    if last < cursor:
        return [], None
    while cursor <= last:
        span = min(CALENDAR_MAX_DAYS, (last - cursor).days + 1)
        path = f"/calendars/all/shows/{cursor.isoformat()}/{span}"
        payload, err, _hdrs = trakt_get(path, client_id)
        if err:
            return None, err
        if isinstance(payload, list):
            items.extend(item for item in payload if isinstance(item, dict))
        cursor = cursor + timedelta(days=span)
    return items, None


def episode_kind(season: int | None, episode: int | None) -> str:
    if season == 1 and episode == 1:
        return "premiere"
    return "episode"


def _event(
    *,
    trakt_id: int,
    title: str,
    when: datetime,
    zone: Any,
    now: datetime,
    season: int | None,
    episode: int | None,
    last: tuple[int, int],
    list_status: str,
    kind: str,
) -> dict[str, Any]:
    local = when.astimezone(zone)
    if local <= now:
        state = "now" if now - local <= timedelta(hours=1) else "aired"
    else:
        state = "upcoming"
    day_state = "today" if local.date() == now.date() and state != "now" else state
    pair = (
        (season or 0, episode or 0)
        if season is not None and episode is not None
        else None
    )
    watched = bool(pair and pair <= last and last != (0, 0))
    if pair and last == (0, 0):
        watched = False
    behind = bool(pair and state == "aired" and not watched)
    progress_ep = last[1] if last != (0, 0) and last[0] == (season or 0) else (
        last[1] if last != (0, 0) else 0
    )
    return {
        "trakt_id": trakt_id,
        "title": title,
        "season": season,
        "episode": episode,
        "progress": progress_ep,
        "watched": watched,
        "behind": behind,
        "airing_at": int(when.timestamp()),
        "start": local.isoformat(),
        "date": local.date().isoformat(),
        "kind": kind,
        "state": state,
        "day_state": day_state,
        "list_status": list_status,
        "media_type": "show",
        "source": "trakt",
    }


def assemble_events(
    calendar_rows: list[dict[str, Any]],
    tracked: dict[int, dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    zone: Any,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, int | None, int | None]] = set()
    for row in calendar_rows:
        sid = show_trakt_id(row)
        if sid is None or sid not in tracked:
            continue
        when = _parse_air(row.get("first_aired"))
        if when is None or when < start or when > end:
            continue
        ep = row.get("episode") if isinstance(row.get("episode"), dict) else {}
        season = _to_int(ep.get("season"))
        number = _to_int(ep.get("number"))
        key = (sid, season, number)
        if key in seen:
            continue
        seen.add(key)
        info = tracked[sid]
        title = info.get("title") or show_title(row)
        events.append(
            _event(
                trakt_id=sid,
                title=title,
                when=when,
                zone=zone,
                now=now,
                season=season,
                episode=number,
                last=info.get("last") or (0, 0),
                list_status=str(info.get("list_status") or "watching"),
                kind=episode_kind(season, number),
            )
        )
    events.sort(key=lambda e: e.get("airing_at") or 0)
    return events


def window_bounds(now: datetime, options: dict[str, Any], view: str) -> tuple[datetime, datetime]:
    if view == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        first_wd = start.weekday()
        week_start = str(options.get("week_start") or "monday")
        want = 6 if week_start == "sunday" else 0
        lead = (first_wd - want) % 7
        grid_start = start - timedelta(days=lead)
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        month_end = start + timedelta(days=days_in_month)
        trail = (7 - ((days_in_month + lead) % 7)) % 7
        grid_end = month_end + timedelta(days=trail)
        return grid_start, grid_end
    try:
        days_back = max(0, int(options.get("days_back") or 0))
    except (TypeError, ValueError):
        days_back = 0
    try:
        days_ahead = max(0, int(options.get("days_ahead") or 0))
    except (TypeError, ValueError):
        days_ahead = 0
    if view == "releases" and days_ahead == 0 and days_back == 0:
        days_back = 7
    if view == "agenda" and days_ahead == 0 and days_back == 0:
        days_back = 2
        days_ahead = 14
    start = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59, microsecond=0)
    if view == "releases":
        end = now
    return start, end


def group_days(
    events: list[dict[str, Any]], start: datetime, end: datetime, zone: Any, now: datetime
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_date.setdefault(str(ev.get("date") or ""), []).append(ev)
    days: list[dict[str, Any]] = []
    cursor = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    today = now.astimezone(zone).date()
    while cursor <= last:
        iso = cursor.isoformat()
        days.append(
            {
                "date": iso,
                "day": cursor.day,
                "weekday": cursor.weekday(),
                "is_today": cursor == today,
                "events": by_date.get(iso, []),
            }
        )
        cursor = cursor + timedelta(days=1)
    return days


def month_grid(
    events: list[dict[str, Any]],
    year: int,
    month: int,
    week_start: str,
    today: datetime,
) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_date.setdefault(str(ev.get("date") or ""), []).append(ev)
    first_wd = calendar.monthrange(year, month)[0]
    want = 6 if week_start == "sunday" else 0
    lead = (first_wd - want) % 7
    start = datetime(year, month, 1, tzinfo=today.tzinfo) - timedelta(days=lead)
    days_in_month = calendar.monthrange(year, month)[1]
    total = lead + days_in_month
    trail = (7 - (total % 7)) % 7
    cells = lead + days_in_month + trail
    today_d = today.date()
    out: list[dict[str, Any]] = []
    for i in range(cells):
        d = (start + timedelta(days=i)).date()
        iso = d.isoformat()
        day_events = by_date.get(iso, [])
        out.append(
            {
                "date": iso,
                "day": d.day,
                "in_month": d.month == month,
                "is_today": d == today_d,
                "weekday": d.weekday(),
                "events": day_events,
                "total": len(day_events),
            }
        )
    return out


def _cache_dir(ctx: dict[str, Any]) -> Path | None:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            core = (current_app.config.get("PLUGIN_REGISTRY") or {}).get("trakt_core")
            if core is not None and getattr(core, "data_dir", None):
                path = Path(core.data_dir)
                path.mkdir(parents=True, exist_ok=True)
                return path
    except Exception:
        pass
    raw = ctx.get("data_dir")
    if not raw:
        return None
    base = Path(raw)
    path = base if base.name == "trakt_core" else base.parent / "trakt_core"
    with contextlib.suppress(OSError):
        path.mkdir(parents=True, exist_ok=True)
        return path
    return None


def _cache_key(username: str, status: str, start: datetime, end: datetime, view: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", f"{username}_{status}_{view}")
    return f"{safe}_{start.date().isoformat()}_{end.date().isoformat()}.json"


def _read_cache(path: Path, ttl: int) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - path.stat().st_mtime < ttl:
        return payload
    payload["_stale_file"] = True
    return payload


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    with contextlib.suppress(OSError):
        path.write_text(json.dumps(payload), encoding="utf-8")


def _int_opt(options: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(options.get(name) if options.get(name) not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def load_schedule(
    options: dict[str, Any],
    ctx: dict[str, Any],
    *,
    view: str = "agenda",
) -> dict[str, Any]:
    username = parse_username(str(options.get("username") or "")) or get_default_username()
    status = list_status_of(str(options.get("list_status") or "watching"))
    client_id = get_client_id()
    if not username:
        return {"error": ERR_NO_USER}
    if not _USER_RE.match(username):
        return {"error": ERR_BAD_USER}
    if not client_id:
        return {"error": ERR_NO_CLIENT}

    zone = _timezone()
    now = datetime.now(zone)
    start, end = window_bounds(now, options, view)
    ttl = max(10, _int_opt(options, "refresh_min", 20)) * 60

    cache_path = None
    cache_dir = _cache_dir(ctx)
    cached = None
    if cache_dir is not None:
        cache_path = cache_dir / _cache_key(username, status, start, end, view)
        cached = _read_cache(cache_path, ttl)
        if cached is not None and not cached.get("_stale_file"):
            cached.pop("_stale_file", None)
            return cached

    tracked, err = fetch_tracked(username, status, client_id)
    if err or tracked is None:
        if cached:
            cached["stale"] = True
            cached.pop("_stale_file", None)
            return cached
        return {"error": err or ERR_UPSTREAM}

    rows, err = fetch_calendar(client_id, start, end)
    if err or rows is None:
        if cached:
            cached["stale"] = True
            cached.pop("_stale_file", None)
            return cached
        return {"error": err or ERR_UPSTREAM}

    events = assemble_events(rows, tracked, start=start, end=end, now=now, zone=zone)
    payload: dict[str, Any] = {
        "username": username,
        "list_status": status,
        "list_label": LIST_LABELS.get(status, status),
        "timezone": str(getattr(zone, "key", None) or zone),
        "now": now.isoformat(),
        "today": now.date().isoformat(),
        "year": now.year,
        "month": now.month,
        "window_start": start.date().isoformat(),
        "window_end": end.date().isoformat(),
        "events": events,
        "shows": len(tracked),
        "list_count": len(tracked),
        "aired": sum(1 for e in events if e.get("state") == "aired"),
        "upcoming": sum(1 for e in events if e.get("state") == "upcoming"),
        "stale": False,
        "view": view,
    }
    if view == "month":
        payload["days"] = month_grid(
            events,
            now.year,
            now.month,
            str(options.get("week_start") or "monday"),
            now,
        )
        payload["week_start"] = str(options.get("week_start") or "monday")
        payload["month_name"] = now.strftime("%B")
    else:
        payload["days"] = group_days(events, start, end, zone, now)

    if cache_path is not None:
        _write_cache(cache_path, payload)
    return payload
