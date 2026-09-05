// trakt_schedule — Spectra agenda of episode air dates, grouped by day.
// Primary target: one column of an 800×480 panel (≈400×480). Timeline
// rail + time chip; accent-4 = today/live, accent-3 = aired, accent-1 =
// on now, accent-2 = unwatched catch-up.

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "<", ">": ">", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtTime(iso, format) {
  if (typeof iso !== "string" || !iso) return "";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "";
  const h = d.getHours();
  const m = d.getMinutes();
  if (format === "12h") {
    const h12 = h % 12 === 0 ? 12 : h % 12;
    const suffix = h < 12 ? "am" : "pm";
    return m === 0 ? `${h12}${suffix}` : `${h12}:${String(m).padStart(2, "0")}${suffix}`;
  }
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function localizedWeekday(date, locale) {
  return new Intl.DateTimeFormat(locale || "en", { weekday: "short" }).format(date);
}

function localizedMonth(date, locale) {
  return new Intl.DateTimeFormat(locale || "en", { month: "short" }).format(date);
}

function parseDate(iso) {
  if (typeof iso !== "string" || !iso) return null;
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function kindLabel(ev, t) {
  if (ev.kind === "premiere") return t("premiere", "Premiere");
  if (ev.kind === "finale") return t("finale", "Finale");
  if (ev.kind === "movie") return t("movie", "Movie");
  if (ev.season != null && ev.episode != null) {
    const s = String(ev.season).padStart(2, "0");
    const e = String(ev.episode).padStart(2, "0");
    return `S${s}E${e}`;
  }
  if (ev.episode != null) return `${t("episode", "Ep")} ${ev.episode}`;
  return "";
}

function isWatched(ev) {
  if (ev.watched === true) return true;
  if (ev.watched === false) return false;
  const ep = Number(ev.episode);
  const prog = Number(ev.progress);
  return Number.isFinite(ep) && Number.isFinite(prog) && prog >= ep;
}

function checkmark(label) {
  return `<span class="ev-check" aria-label="${escapeHtml(label)}">✓</span>`;
}

function stateAccent(ev) {
  if (ev.state === "now") return "var(--accent-1)";
  if (ev.behind) return "var(--accent-2)";
  if (isWatched(ev)) return "var(--accent-3)";
  if (ev.state === "aired") return "var(--accent-3)";
  return "var(--accent-4)";
}

function renderEvent(ev, timeFormat, t) {
  const accent = stateAccent(ev);
  const time = fmtTime(ev.start, timeFormat);
  const kind = kindLabel(ev, t);
  const watched = isWatched(ev);
  const behind = ev.behind ? t("behind", "Behind") : "";
  const state = ev.state === "now" ? t("now", "Now") : "";
  const seen = watched ? t("watched", "Watched") : "";
  const meta = [kind, behind || state || seen].filter(Boolean).join(" · ");
  const mark = watched ? checkmark(t("watched", "Watched")) : "";
  return `
    <div class="rail-row${ev.state === "now" ? " is-now" : ""}${ev.behind ? " is-behind" : ""}${watched ? " is-watched" : ""}">
      <span class="time-chip" style="background:${accent};color:var(--on-accent)">${escapeHtml(time || "—")}</span>
      <span class="rail-node" style="background:${accent}"></span>
      <div class="ev-body">
        <div class="ev-title"><span class="ev-name">${escapeHtml(ev.title || "")}</span>${kind ? `<span class="ev-ep">${escapeHtml(kind)}</span>` : ""}${mark}</div>
        ${meta ? `<div class="ev-sub">${escapeHtml(meta)}</div>` : ""}
      </div>
    </div>`;
}

function renderDay(day, timeFormat, t, locale) {
  const date = parseDate(day.date);
  const num = day.day ?? (date ? date.getDate() : "");
  const dow = date ? localizedWeekday(date, locale) : "";
  const mon = date ? localizedMonth(date, locale) : "";
  const events = Array.isArray(day.events) ? day.events : [];
  const rows = events.map((ev) => renderEvent(ev, timeFormat, t)).join("");
  const empty = events.length === 0
    ? `<div class="ev-empty">${escapeHtml(t("no_events", "No episodes"))}</div>`
    : "";
  return `
    <section class="day${day.is_today ? " is-today" : ""}">
      <header class="day-header">
        <span class="day-num">${escapeHtml(String(num))}</span>
        <span class="day-dow">${escapeHtml(dow)}</span>
        <span class="day-mon">${escapeHtml(mon)}</span>
      </header>
      <div class="day-rail">${rows}${empty}</div>
    </section>`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const opts = ctx?.cell?.options || {};
  const size = ctx?.cell?.size || "md";
  const cellW = Number(ctx?.cell?.w) || 0;
  const cellH = Number(ctx?.cell?.h) || 0;
  const locale = ctx?.locale || "en";
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const timeFormat = opts.time_format === "12h" ? "12h" : "24h";
  const skipEmpty = opts.skip_empty !== false;
  const showTitle = opts.show_title !== false;
  const title = (opts.title || "").trim() || t("schedule", "Schedule");
  const listLabel = data.list_label || t(data.list_status || "watching", "Watching");
  const narrow = cellW > 0 ? cellW <= 440 : size === "xs" || size === "sm";

  const css = `
    <link rel="stylesheet" href="/static/style/spectra-widgets.css">
    <style>
      :host { display:block; width:100%; height:100%; overflow:hidden; container-type: size; }
      .w { height:100%; display:flex; flex-direction:column; min-height:0; }
      .w-body { flex:1 1 auto; min-height:0; overflow:hidden; }
      .days {
        height:100%;
        column-gap: 1.25em;
        column-fill: auto;
      }
      .w[data-cols="2"] .days { column-count: 2; }
      .w[data-cols="3"] .days { column-count: 3; }
      .day { break-inside: avoid; margin: 0 0 0.55em; }
      .day-header {
        display: flex;
        align-items: baseline;
        gap: 0.35em;
        margin-bottom: 0.2em;
      }
      .day-num {
        font-size: calc(var(--fs-lead) * 1.05);
        font-weight: var(--fw-black);
        font-variant-numeric: tabular-nums;
        line-height: 1;
        color: var(--text-primary);
      }
      .day.is-today .day-num {
        background: var(--accent-4);
        color: var(--on-accent);
        width: 1.35em;
        height: 1.35em;
        display: inline-grid;
        place-items: center;
        border-radius: var(--pill-radius, 999px);
        font-size: var(--fs-caption);
      }
      .day-dow {
        font-size: var(--fs-label);
        font-weight: var(--fw-bold);
        letter-spacing: var(--ls-label, 0.04em);
        text-transform: var(--label-transform, uppercase);
        color: var(--text-secondary);
      }
      .day.is-today .day-dow { color: var(--accent-4); }
      .day-mon {
        font-size: var(--fs-caption);
        font-weight: var(--fw-semi);
        color: var(--text-muted);
        text-transform: var(--label-transform, uppercase);
      }
      .day-rail { position: relative; }
      .day-rail::before {
        content: "";
        position: absolute;
        left: calc(3.55em + 0.42em);
        top: 0.15em;
        bottom: 0.15em;
        width: var(--edge-weight, 2px);
        background: var(--surface-sunken);
      }
      .rail-row {
        display: grid;
        grid-template-columns: 3.55em 0.85em minmax(0, 1fr);
        align-items: start;
        gap: 0.25em;
        padding: 0.1em 0;
        break-inside: avoid;
        position: relative;
      }
      .time-chip {
        font-size: var(--fs-caption);
        font-weight: var(--fw-black);
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.01em;
        text-align: center;
        padding: 0.12em 0.15em;
        border-radius: var(--pill-radius, var(--radius-1));
        line-height: 1.15;
      }
      .rail-node {
        width: 0.45em;
        height: 0.45em;
        border-radius: 999px;
        margin-top: 0.38em;
        justify-self: center;
        z-index: 1;
        box-shadow: 0 0 0 2px var(--surface);
      }
      .ev-title {
        font-size: var(--fs-body);
        font-weight: var(--fw-bold);
        line-height: 1.15;
        min-width: 0;
        display: flex;
        align-items: center;
        gap: 0.35em;
      }
      .ev-name {
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        min-width: 0;
        flex: 1 1 auto;
      }
      .ev-ep {
        display: none;
        flex: 0 0 auto;
        font-size: var(--fs-caption);
        font-weight: var(--fw-semi);
        color: var(--text-muted);
      }
      .ev-check {
        flex: 0 0 auto;
        font-size: 0.95em;
        font-weight: var(--fw-black);
        line-height: 1;
        color: var(--accent-3);
      }
      .ev-sub {
        font-size: var(--fs-caption);
        font-weight: var(--fw-semi);
        color: var(--text-muted);
        margin-top: 0.02em;
      }
      .ev-empty {
        font-size: var(--fs-caption);
        color: var(--text-muted);
        padding: 0.15em 0 0.15em 4.5em;
      }
      .empty-body {
        display: grid;
        place-items: center;
        height: 100%;
        color: var(--text-muted);
        font-weight: var(--fw-semi);
        text-align: center;
        padding: var(--space-4);
      }

      /* 400-wide panel column (half of 800×480). Keep one agenda
         column, drop the rail, put Ep on the title line. */
      @container (max-width: 440px) {
        .day-mon { display: none; }
        .ev-sub { display: none; }
        .ev-ep { display: block; }
        .rail-node { display: none; }
        .day-rail::before { display: none; }
        .rail-row { grid-template-columns: 3.15em minmax(0, 1fr); gap: 0.4em; }
        .day { margin: 0 0 0.35em; }
        .day-num { font-size: var(--fs-body); }
        .ev-title { font-size: calc(var(--fs-body) * 0.95); }
        .w[data-cols="2"] .days,
        .w[data-cols="3"] .days { column-count: 1; }
        .w-title-meta {
          max-width: 42%;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      }
      @container (max-width: 360px) {
        .time-chip { font-size: calc(var(--fs-caption) * 0.95); }
        .rail-row { grid-template-columns: 2.9em minmax(0, 1fr); }
      }
    </style>
  `;

  if (data.error) {
    shadow.innerHTML = `
      ${css}
      <div class="w" data-widget="trakt_schedule">
        <div class="w-title">
          <i class="ph-bold ph-warning-circle" aria-hidden="true"></i>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <div class="w-body cal-body"><div class="empty-body">${escapeHtml(data.error)}</div></div>
      </div>`;
    return;
  }

  let days = Array.isArray(data.days) ? data.days.slice() : [];
  if (skipEmpty) days = days.filter((d) => Array.isArray(d.events) && d.events.length);
  const cap = cellH > 0
    ? Math.max(5, Math.floor((cellH - 36) / (narrow ? 32 : 40)))
    : ({ xs: 3, sm: 6, md: 12, lg: 28 }[size] || 12);
  const headerCost = narrow ? 0.8 : 0;

  function packDays(list, budget) {
    const out = [];
    let used = 0;
    for (const d of list) {
      const events = Array.isArray(d.events) ? d.events : [];
      const remaining = budget - used;
      if (remaining <= headerCost) break;
      const room = Math.max(0, Math.floor(remaining - headerCost));
      const sliced = events.slice(0, room);
      if (!sliced.length) {
        if (skipEmpty) continue;
        out.push({ ...d, events: [] });
        used += headerCost;
        continue;
      }
      out.push({ ...d, events: sliced });
      used += headerCost + sliced.length;
    }
    return out;
  }

  days = packDays(days, cap);

  let cols = String(opts.columns || "auto");
  if (cols === "auto") {
    cols = cellW > 0 ? (cellW >= 700 ? "2" : "1") : (size === "lg" ? "2" : "1");
  }
  if (narrow) cols = "1";
  if (!["1", "2", "3"].includes(cols)) cols = "1";

  const meta = [listLabel, data.username].filter(Boolean).join(" · ");
  const dayHtml = days.map((d) => renderDay(d, timeFormat, t, locale)).join("");
  const body = days.length
    ? `<div class="days">${dayHtml}</div>`
    : `<div class="empty-body">${escapeHtml(t("empty", "Nothing airing in this window."))}</div>`;

  const titleHtml = showTitle ? `
    <div class="w-title">
      <i class="ph-bold ph-list-bullets" aria-hidden="true" style="color:var(--accent-4)"></i>
      <h3>${escapeHtml(title)}</h3>
      <span class="w-title-meta">${escapeHtml(meta)}</span>
    </div>` : "";

  shadow.innerHTML = `
    ${css}
    <div class="w size-${escapeHtml(size)}" data-widget="trakt_schedule" data-cols="${escapeHtml(cols)}" data-narrow="${narrow ? "1" : "0"}">
      ${titleHtml}
      <div class="w-body cal-body">${body}</div>
    </div>`;
}
