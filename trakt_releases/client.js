// trakt_releases — Spectra list of recently aired episodes from a Trakt list.

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "<", ">": ">", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function fmtWhen(iso, locale) {
  if (typeof iso !== "string" || !iso) return "";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "";
  const deltaH = (Date.now() - d.getTime()) / 36e5;
  if (deltaH < 0) {
    return new Intl.DateTimeFormat(locale || "en", { weekday: "short", day: "numeric", month: "short" }).format(d);
  }
  if (deltaH < 1) return "now";
  if (deltaH < 24) return `${Math.max(1, Math.round(deltaH))}h`;
  return new Intl.DateTimeFormat(locale || "en", { weekday: "short", day: "numeric", month: "short" }).format(d);
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const opts = ctx?.cell?.options || {};
  const size = ctx?.cell?.size || "md";
  const locale = ctx?.locale || "en";
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const showTitle = opts.show_title !== false;
  const title = (opts.title || "").trim() || t("releases", "Releases");

  const css = `
    <link rel="stylesheet" href="/static/style/spectra-widgets.css">
    <style>
      :host { display:block; width:100%; height:100%; overflow:hidden; container-type: size; }
      .w { height:100%; display:flex; flex-direction:column; min-height:0; }
      .w-body { flex:1 1 auto; min-height:0; overflow:hidden; }
      .rel-row {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: var(--space-2);
        align-items: center;
        padding: 0.28em 0;
      }
      .rel-row + .rel-row {
        box-shadow: inset 0 var(--row-rule-w, 0px) 0 var(--surface-sunken);
      }
      .rel-row:nth-child(even) { background: var(--zebra-bg, transparent); }
      .rel-title {
        font-size: var(--fs-body);
        font-weight: var(--fw-bold);
        line-height: 1.15;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        display: flex;
        align-items: center;
        gap: 0.35em;
        min-width: 0;
      }
      .rel-title > span:first-child {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        min-width: 0;
      }
      .rel-title .pill { flex: 0 0 auto; }
      .ev-check {
        flex: 0 0 auto;
        font-size: 1em;
        font-weight: var(--fw-black);
        line-height: 1;
        color: var(--accent-3);
      }
      .rel-sub {
        font-size: var(--fs-caption);
        font-weight: var(--fw-semi);
        color: var(--text-muted);
        margin-top: 0.05em;
      }
      .rel-when {
        font-size: var(--fs-caption);
        font-weight: var(--fw-black);
        font-variant-numeric: tabular-nums;
        color: var(--text-secondary);
        text-align: right;
      }
      .pill {
        display: inline-block;
        padding: 0.05em 0.4em;
        border-radius: var(--pill-radius, 999px);
        font-size: calc(var(--fs-caption) * 0.9);
        font-weight: var(--fw-bold);
        letter-spacing: var(--ls-label, 0.03em);
        text-transform: var(--label-transform, uppercase);
        background: var(--accent-2-soft);
        color: var(--accent-2);
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
      @container (max-width: 440px) {
        .rel-title { font-size: calc(var(--fs-body) * 0.92); }
        .rel-row { padding: 0.12em 0; gap: var(--space-1); }
      }
      @container (max-height: 280px) {
        .rel-sub { display: none; }
        .rel-row:nth-child(n+5) { display: none; }
      }
      @container (min-height: 281px) and (max-height: 400px) {
        .rel-row:nth-child(n+8) { display: none; }
      }
      @container (min-height: 401px) and (max-height: 520px) {
        .rel-row:nth-child(n+11) { display: none; }
      }
    </style>
  `;

  if (data.error) {
    shadow.innerHTML = `
      ${css}
      <div class="w" data-widget="trakt_releases">
        <div class="w-title">
          <i class="ph-bold ph-warning-circle" aria-hidden="true"></i>
          <h3>${escapeHtml(title)}</h3>
        </div>
        <div class="w-body list-body"><div class="empty-body">${escapeHtml(data.error)}</div></div>
      </div>`;
    return;
  }

  const events = Array.isArray(data.events) ? data.events : [];
  const meta = [data.list_label, data.username].filter(Boolean).join(" · ");
  const rows = events.map((ev) => {
    const ep = (ev.season != null && ev.episode != null)
    ? `S${String(ev.season).padStart(2, "0")}E${String(ev.episode).padStart(2, "0")}`
    : (ev.episode != null ? `${t("episode", "Ep")} ${ev.episode}` : (ev.kind || ""));
    const watched = ev.watched === true || (
      ev.watched !== false
      && ev.episode != null
      && ev.progress != null
      && Number(ev.progress) >= Number(ev.episode)
    );
    const sub = ep;
    const mark = watched
      ? `<span class="ev-check" aria-label="${escapeHtml(t("watched", "Watched"))}">✓</span>`
      : (ev.behind ? `<span class="pill">${escapeHtml(t("behind", "Behind"))}</span>` : "");
    return `
      <div class="rel-row list-row${watched ? " is-watched" : ""}${ev.behind ? " is-behind" : ""}">
        <div class="list-lead">
          <div class="rel-title"><span>${escapeHtml(ev.title || "")}</span>${mark}</div>
          ${sub ? `<div class="rel-sub">${escapeHtml(sub)}</div>` : ""}
        </div>
        <div class="rel-when">${escapeHtml(fmtWhen(ev.start, locale))}</div>
      </div>`;
  }).join("");

  const titleHtml = showTitle ? `
    <div class="w-title">
      <i class="ph-bold ph-broadcast" aria-hidden="true" style="color:var(--accent-3)"></i>
      <h3>${escapeHtml(title)}</h3>
      <span class="w-title-meta">${escapeHtml(meta || String(events.length))}</span>
    </div>` : "";

  const body = events.length
    ? rows
    : `<div class="empty-body">${escapeHtml(t("empty", "Nothing from this list has aired in the window."))}</div>`;

  shadow.innerHTML = `
    ${css}
    <div class="w size-${escapeHtml(size)}" data-widget="trakt_releases">
      ${titleHtml}
      <div class="w-body list-body">${body}</div>
    </div>`;
}
