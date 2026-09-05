// trakt_month — Spectra month grid of episode air dates from a Trakt list.

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "<", ">": ">", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function heatBackground(count) {
  if (count <= 0) return "";
  const intensity = Math.min(1, count / 4);
  const alpha = 8 + 22 * intensity;
  return `background: color-mix(in oklab, var(--accent-4) ${alpha.toFixed(0)}%, var(--surface));`;
}

function weekdayLabels(weekStart, locale, compact) {
  const monday = new Date(2026, 0, 5);
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const full = new Intl.DateTimeFormat(locale || "en", { weekday: compact ? "narrow" : "short" }).format(d);
    days.push(full);
  }
  if (weekStart === "sunday") return [days[6], ...days.slice(0, 6)];
  return days;
}

function eventAccent(ev) {
  if (ev.state === "now") return "var(--accent-1)";
  if (ev.behind) return "var(--accent-2)";
  if (ev.state === "aired") return "var(--accent-3)";
  return "var(--accent-4)";
}

function shortTitle(ev) {
  const name = ev.title || "";
  const ep = ev.episode != null ? ` ${ev.episode}` : "";
  return `${name}${ep}`;
}

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const opts = ctx?.cell?.options || {};
  const size = ctx?.cell?.size || "md";
  const locale = ctx?.locale || "en";
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const weekStart = data.week_start === "sunday" ? "sunday" : "monday";
  const narrow = (Number(ctx?.cell?.w) || 0) > 0 && Number(ctx.cell.w) <= 440;
  const display = opts.event_display === "dots" || narrow ? "dots" : "titles";
  const maxPerDay = Math.max(1, Number(opts.max_per_day) || 3);
  const showTitle = opts.show_title !== false;

  const css = `
    <link rel="stylesheet" href="/static/style/spectra-widgets.css">
    <style>
      :host { display:block; width:100%; height:100%; overflow:hidden; container-type: size; }
      .w { height:100%; display:flex; flex-direction:column; min-height:0; }
      .w-body { flex:1 1 auto; min-height:0; }
      .mc {
        height:100%;
        display: grid;
        grid-template-columns: repeat(7, minmax(0, 1fr));
        grid-template-rows: auto repeat(var(--mc-weeks, 6), minmax(0, 1fr));
        gap: 2px;
      }
      .mc-dow {
        font-size: var(--fs-caption);
        font-weight: var(--fw-black);
        letter-spacing: var(--ls-label, 0.04em);
        text-transform: var(--label-transform, uppercase);
        color: var(--text-muted);
        text-align: center;
        padding: 0.15em 0;
      }
      .mc-cell {
        min-height: 0;
        padding: var(--space-1);
        display: flex;
        flex-direction: column;
        gap: 0.15em;
        overflow: hidden;
      }
      .mc-cell.is-out { opacity: 0.38; }
      .mc-num {
        font-size: var(--fs-caption);
        font-weight: var(--fw-black);
        font-variant-numeric: tabular-nums;
        color: var(--text-secondary);
        line-height: 1.1;
      }
      .mc-cell.is-today .mc-num {
        background: var(--accent-4);
        color: var(--on-accent);
        width: 1.5em;
        height: 1.5em;
        display: inline-grid;
        place-items: center;
        border-radius: var(--pill-radius, 999px);
      }
      .mc-dots {
        display: flex;
        flex-wrap: wrap;
        gap: 3px;
        margin-top: auto;
      }
      .mc-dot {
        width: 0.45em;
        height: 0.45em;
        border-radius: 999px;
      }
      .mc-text {
        font-size: calc(var(--fs-caption) * 0.92);
        font-weight: var(--fw-semi);
        line-height: 1.15;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
      }
      .mc-more {
        font-size: var(--fs-caption);
        font-weight: var(--fw-black);
        color: var(--text-muted);
        font-variant-numeric: tabular-nums;
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
        .mc-dow { font-size: calc(var(--fs-caption) * 0.9); letter-spacing: 0; }
        .mc-text { display: none; }
        .mc-more { display: none; }
        .mc-cell { padding: 0.12em 0.08em; align-items: center; }
        .mc-dots { justify-content: center; gap: 2px; }
        .mc-dot { width: 0.38em; height: 0.38em; }
        .mc-num { font-size: calc(var(--fs-caption) * 0.95); }
        .mc-cell.is-today .mc-num {
          width: 1.35em;
          height: 1.35em;
        }
      }
    </style>
  `;

  if (data.error) {
    shadow.innerHTML = `
      ${css}
      <div class="w" data-widget="trakt_month">
        <div class="w-title">
          <i class="ph-bold ph-warning-circle" aria-hidden="true"></i>
          <h3>${escapeHtml(t("month", "Month"))}</h3>
        </div>
        <div class="w-body cal-body"><div class="empty-body">${escapeHtml(data.error)}</div></div>
      </div>`;
    return;
  }

  const days = Array.isArray(data.days) ? data.days : [];
  const monthDate = new Date(data.year || 2026, (data.month || 1) - 1, 1);
  const monthName = new Intl.DateTimeFormat(locale, { month: "long" }).format(monthDate);
  const year = data.year || "";
  const meta = [data.list_label, data.username].filter(Boolean).join(" · ");

  const dow = weekdayLabels(weekStart, locale, narrow)
    .map((label) => `<div class="mc-dow">${escapeHtml(label)}</div>`)
    .join("");

  const cells = days.map((d) => {
    const events = Array.isArray(d.events) ? d.events : [];
    const count = events.length;
    const classes = ["mc-cell"];
    if (!d.in_month) classes.push("is-out");
    if (d.is_today) classes.push("is-today");
    const heat = d.in_month ? heatBackground(count) : "";
    let body = "";
    if (display === "dots") {
      body = `<div class="mc-dots">${events.slice(0, 6).map((ev) =>
        `<span class="mc-dot" style="background:${eventAccent(ev)}"></span>`
      ).join("")}</div>`;
    } else {
      const visible = events.slice(0, (size === "sm" || (Number(ctx?.cell?.w) || 0) <= 440) ? 1 : maxPerDay);
      const extra = count - visible.length;
      body = visible.map((ev) =>
        `<div class="mc-text" style="color:${eventAccent(ev)}">${escapeHtml(shortTitle(ev))}</div>`
      ).join("");
      if (extra > 0) body += `<div class="mc-more">+${extra}</div>`;
    }
    return `<div class="${classes.join(" ")}" style="${heat}">
      <span class="mc-num">${escapeHtml(String(d.day ?? ""))}</span>
      ${body}
    </div>`;
  }).join("");

  const titleHtml = showTitle ? `
    <div class="w-title">
      <i class="ph-bold ph-calendar" aria-hidden="true" style="color:var(--accent-4)"></i>
      <h3>${escapeHtml(monthName)} ${escapeHtml(String(year))}</h3>
      <span class="w-title-meta">${escapeHtml(meta)}</span>
    </div>` : "";

  const weeks = Math.max(4, Math.ceil(days.length / 7) || 5);

  shadow.innerHTML = `
    ${css}
    <div class="w size-${escapeHtml(size)}" data-widget="trakt_month">
      ${titleHtml}
      <div class="w-body cal-body">
        <div class="mc" style="--mc-weeks:${weeks}">${dow}${cells}</div>
      </div>
    </div>`;
}
