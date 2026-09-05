# Trakt widgets for Tesserae

Episode air dates from a public [Trakt](https://trakt.tv/) profile, painted for e-ink dashboards.

Three layouts share one data plugin:

| Folder | Widget | Best for |
| --- | --- | --- |
| `trakt_schedule` | **Trakt, Schedule** | Day-by-day agenda (the one you'll probably keep on the panel) |
| `trakt_month` | **Trakt, Month** | Heat-tinted month grid |
| `trakt_releases` | **Trakt, Releases** | What just dropped, newest first |

Each cell picks a **username** and a **list** (Watching = shows you've watched at least one episode of, Watchlist, Collection, or all three).

Layouts are built for a **400×480 column** — half of an 800×480 panel (Seeed / Waveshare 7.3") with two widgets side by side. Schedule stays a single-column agenda at that width.

## Data

1. A **Trakt Client ID** is required. Public profiles still go through `api.trakt.tv`; create an app at [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications) and paste only the Client ID into **Trakt Core**. Redirect `urn:ietf:wg:oauth:2.0:oob` is fine — this bundle does not use OAuth.
2. The chosen list is read from the public user endpoints (`/users/{id}/watched/shows`, watchlist, collection).
3. [Trakt's global show calendar](https://trakt.docs.apiary.io/#reference/calendars) is filtered to those show ids. Air timestamps are already on each calendar row.

The profile must be **public**. Times follow Tesserae's app timezone setting. Set your Trakt username in **Trakt Core** (or per cell).

## Setup

Tesserae loads **sibling** folders under `plugins/` (`plugins/trakt_core/plugin.json`, …). Cloning this repo *into* `plugins/` nests them one level too deep and the loader will ignore them.

**Git (this repo):** clone anywhere, then symlink the four plugin folders:

```bash
git clone https://github.com/Bestora/tesserae-widget-trakt.git
./tesserae-widget-trakt/install.sh /path/to/tesserae/plugins
```

On the official Docker compose layout the plugin *code* lives in the data volume's `marketplace/` folder, not `data/plugins/` (that directory is per-plugin state). From `/opt/tesserae`:

```bash
git clone https://github.com/Bestora/tesserae-widget-trakt.git data/tesserae-widget-trakt
./data/tesserae-widget-trakt/install.sh /opt/tesserae/data/marketplace
docker compose restart
```

`install.sh` links `trakt_core`, `trakt_schedule`, `trakt_month`, and `trakt_releases`. `git pull` in the clone then updates all four. Use `--copy` instead of links if the Tesserae process cannot follow symlinks (some Docker / HA layouts).

Restart Tesserae, then **Settings → Plugins → Trakt Core**: paste the Client ID and a default username. Add **Trakt, Schedule** (and/or Month / Releases) to a dashboard.

## Options (all three widgets)

- **Trakt username** — profile name or a `trakt.tv/users/…` / `app.trakt.tv/profile/…` URL. Blank uses the Core default.
- **List** — watched shows, watchlist, collection, or the union.
- **Cache minutes** — default 20. Don't go below 10.

Schedule also has look-back / look-ahead, skip-empty-days, 12/24h time, and column count. Month has week-start and titles-vs-dots. Releases has look-back and a row cap.

## Network

Declared in each `plugin.json`:

- `network:api.trakt.tv`
- `settings:plugin/trakt_core`
- `settings:app` (timezone)

No filesystem writes outside the plugin `data_dir`. The Client ID is stored as a secret.

## Develop

```bash
python3 -m pytest trakt_core/tests -q
```

Run `./install.sh /path/to/tesserae/plugins` and open `/_test/render?plugin=trakt_schedule&size=md`.

A layout sheet that fetches the live **bestora** watched list (needs `TRAKT_CLIENT_ID` in the environment):

```bash
TRAKT_CLIENT_ID=… python3 preview/serve.py   # http://127.0.0.1:8767/preview/
```
