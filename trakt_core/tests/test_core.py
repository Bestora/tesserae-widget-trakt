"""Pure unit tests for trakt_core. No Tesserae host required."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "server.py"


def load():
    spec = importlib.util.spec_from_file_location("trakt_core_server", ROOT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = load()
BERLIN = ZoneInfo("Europe/Berlin")


def test_parse_username_from_urls_and_handle():
    assert core.parse_username("https://app.trakt.tv/profile/bestora") == "bestora"
    assert core.parse_username("https://trakt.tv/users/bestora") == "bestora"
    assert core.parse_username("trakt.tv/users/bestora/watchlist") == "bestora"
    assert core.parse_username("@bestora") == "bestora"
    assert core.parse_username("bestora") == "bestora"
    assert core.parse_username("not a name!!!") == ""
    assert core.parse_username("") == ""


def test_list_status_aliases():
    assert core.list_status_of("watchlist") == "watchlist"
    assert core.list_status_of("Plan to Watch") == "watchlist"
    assert core.list_status_of("ptw") == "watchlist"
    assert core.list_status_of("watched") == "watching"
    assert core.list_status_of("nope") == "watching"


def test_last_watched_pair_from_seasons():
    item = {
        "seasons": [
            {
                "number": 1,
                "episodes": [
                    {"number": 1, "plays": 1},
                    {"number": 2, "plays": 1},
                ],
            },
            {
                "number": 2,
                "episodes": [{"number": 1, "plays": 1}, {"number": 2, "plays": 0}],
            },
        ]
    }
    assert core.last_watched_pair(item) == (2, 1)


def test_last_watched_pair_empty():
    assert core.last_watched_pair({}) == (0, 0)
    assert core.last_watched_pair({"seasons": []}) == (0, 0)


def test_behind_when_aired_past_progress():
    now = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    when = now - timedelta(hours=6)
    ev = core._event(
        trakt_id=1,
        title="The Expanse",
        when=when,
        zone=UTC,
        now=now,
        season=2,
        episode=4,
        last=(2, 3),
        list_status="watching",
        kind="episode",
    )
    assert ev["state"] == "aired"
    assert ev["watched"] is False
    assert ev["behind"] is True


def test_watched_when_pair_at_or_behind_last():
    now = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    when = now - timedelta(hours=6)
    ev = core._event(
        trakt_id=1,
        title="The Expanse",
        when=when,
        zone=UTC,
        now=now,
        season=2,
        episode=3,
        last=(2, 3),
        list_status="watching",
        kind="episode",
    )
    assert ev["watched"] is True
    assert ev["behind"] is False


def test_watchlist_aired_is_behind():
    now = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    when = now - timedelta(hours=6)
    ev = core._event(
        trakt_id=9,
        title="New Show",
        when=when,
        zone=UTC,
        now=now,
        season=1,
        episode=1,
        last=(0, 0),
        list_status="watchlist",
        kind="premiere",
    )
    assert ev["watched"] is False
    assert ev["behind"] is True


def test_assemble_filters_to_tracked_ids():
    now = datetime(2026, 9, 5, 12, 0, tzinfo=BERLIN)
    start = now - timedelta(days=2)
    end = now + timedelta(days=10)
    rows = [
        {
            "first_aired": "2026-09-06T18:00:00.000Z",
            "episode": {"season": 1, "number": 4, "title": "Late"},
            "show": {"title": "Mine", "ids": {"trakt": 10}},
        },
        {
            "first_aired": "2026-09-06T18:00:00.000Z",
            "episode": {"season": 1, "number": 4, "title": "Other"},
            "show": {"title": "Not mine", "ids": {"trakt": 99}},
        },
    ]
    tracked = {10: {"id": 10, "title": "Mine", "last": (1, 3), "list_status": "watching"}}
    events = core.assemble_events(rows, tracked, start=start, end=end, now=now, zone=BERLIN)
    assert len(events) == 1
    assert events[0]["trakt_id"] == 10
    assert events[0]["episode"] == 4
    assert events[0]["season"] == 1
    assert events[0]["source"] == "trakt"


def test_group_days_marks_today():
    now = datetime(2026, 9, 5, 10, 0, tzinfo=BERLIN)
    events = [{"date": "2026-09-05", "title": "The Expanse", "airing_at": int(now.timestamp())}]
    days = core.group_days(events, now.replace(hour=0), now.replace(hour=23), BERLIN, now)
    today = next(d for d in days if d["is_today"])
    assert today["date"] == "2026-09-05"
    assert today["events"][0]["title"] == "The Expanse"


def test_month_grid_starts_on_monday_and_pads():
    today = datetime(2026, 9, 5, 10, 0, tzinfo=BERLIN)
    days = core.month_grid([], 2026, 9, "monday", today)
    assert len(days) % 7 == 0
    assert days[0]["weekday"] == 0
    in_month = [d for d in days if d["in_month"]]
    assert len(in_month) == 30
    assert any(d["is_today"] for d in days)


def test_window_agenda_defaults():
    now = datetime(2026, 9, 5, 12, 0, tzinfo=BERLIN)
    start, end = core.window_bounds(now, {}, "agenda")
    assert (now.date() - start.date()).days == 2
    assert (end.date() - now.date()).days == 14


def test_load_schedule_requires_client_id():
    payload = core.load_schedule({"username": "bestora"}, {}, view="agenda")
    assert "error" in payload
    assert "Client ID" in payload["error"]


def test_load_schedule_requires_username():
    original = core.get_client_id
    core.get_client_id = lambda: "fake-id"
    try:
        payload = core.load_schedule({"username": ""}, {}, view="agenda")
    finally:
        core.get_client_id = original
    assert payload.get("error") == core.ERR_NO_USER


def test_fetch_tracked_uses_watched_path_for_watching():
    calls: list[str] = []

    def fake_pages(path, _client_id):
        calls.append(path)
        return [
            {
                "show": {"title": "The Expanse", "ids": {"trakt": 42}},
                "seasons": [{"number": 1, "episodes": [{"number": 1, "plays": 1}]}],
            }
        ], None

    original = core.trakt_get_pages
    core.trakt_get_pages = fake_pages
    try:
        tracked, err = core.fetch_tracked("bestora", "watching", "cid")
    finally:
        core.trakt_get_pages = original
    assert err is None
    assert tracked is not None
    assert 42 in tracked
    assert tracked[42]["last"] == (1, 1)
    assert "/users/bestora/watched/shows" in calls[0]
