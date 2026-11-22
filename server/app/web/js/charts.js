// Gráficas en SVG sin dependencias. Los colores salen de variables CSS (ver app.css, "Task 8").
import { km, n0, dur, monthLong, monthName, dayMonth } from "./fmt.js";

const NS = "http://www.w3.org/2000/svg";
const fMon = new Intl.DateTimeFormat("es-ES", { timeZone: "UTC", month: "long" });
const abbr = (name) => name.slice(0, 3);
const DAY = 86400000;

function s(tag, attrs = {}, ...children) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    n.setAttribute(k, v);
  }
  for (const c of children) n.append(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
}
const title = (t) => s("title", {}, t);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const utc = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
};
const iso = (t) => new Date(t).toISOString().slice(0, 10);

function onActivate(node, fn) {
  node.addEventListener("click", fn);
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fn(); }
  });
}

// Niveles 1..4 según los cuartiles de los km de los días con uso.
function thresholds(days) {
  const v = days.map((d) => d.km).filter((x) => x > 0).sort((a, b) => a - b);
  if (!v.length) return [0, 0, 0];
  const q = (p) => v[Math.min(v.length - 1, Math.floor(p * v.length))];
  return [q(0.25), q(0.5), q(0.75)];
}
const level = (k, [a, b, c]) => (k > 0 ? (k <= a ? 1 : k <= b ? 2 : k <= c ? 3 : 4) : 0);

const CELL = 11, GAP = 3, STEP = CELL + GAP, LEFT = 28, TOP = 18, COLS = 53;

export function heatmap(days, { endDate, today }) {
  const byDate = new Map(days.map((d) => [d.date, d]));
  const th = thresholds(days);
  const end = utc(endDate);
  const dow = (t) => (new Date(t).getUTCDay() + 6) % 7;
  const startDate = iso(end - 364 * DAY);
  const first = end - dow(end) * DAY - (COLS - 1) * 7 * DAY;
  const w = LEFT + COLS * STEP - GAP, h = TOP + 7 * STEP - GAP;
  const total = days.reduce((a, d) => a + d.km, 0);
  const trips = days.reduce((a, d) => a + d.trips, 0);

  const svg = s("svg", {
    class: "hm", viewBox: `0 0 ${w} ${h}`, width: w, height: h, role: "group",
    "aria-label": `Kilómetros de los últimos 12 meses: ${n0(total)} km en ${plural(trips, "trayecto", "trayectos")}`,
  });

  ["lun", "", "mié", "", "vie", "", ""].forEach((t, r) => {
    if (t) svg.append(s("text", { class: "hm-label", x: 0, y: TOP + r * STEP + CELL - 1 }, t));
  });

  let lastLabel = -9, prevMonth = -1;
  for (let c = 0; c < COLS; c++) {
    const monday = first + c * 7 * DAY;
    const mon = new Date(monday).getUTCMonth();
    if (mon !== prevMonth) {
      if (c - lastLabel >= 3) {
        svg.append(s("text", { class: "hm-label", x: LEFT + c * STEP, y: 10 }, abbr(fMon.format(monday))));
        lastLabel = c;
      }
      prevMonth = mon;
    }
    for (let r = 0; r < 7; r++) {
      const t = monday + r * DAY;
      const date = iso(t);
      const future = date > today || date > endDate || date < startDate;
      const d = byDate.get(date);
      const k = d ? d.km : 0;
      const label = dayMonth(date);
      const text = d && d.trips > 0
        ? `${label} · ${km(k)} · ${plural(d.trips, "trayecto", "trayectos")}`
        : `${label} · sin trayectos`;
      const rect = s("rect", {
        class: future ? "hm-cell hm-future" : `hm-cell l${level(k, th)}`,
        x: LEFT + c * STEP, y: TOP + r * STEP, width: CELL, height: CELL, rx: 2,
        role: future ? null : "img", "aria-label": future ? null : text,
        "aria-hidden": future ? "true" : null,
        tabindex: future ? null : "0",
      }, future ? null : title(text));
      if (!future) {
        rect.dataset.date = date;
        rect.dataset.text = text;
        rect.dataset.trips = d ? d.trips : 0;
        onActivate(rect, () => openPop(rect, true));
      }
      svg.append(rect);
    }
  }

  // Popover al tocar un día: vive en la tarjeta (host) y se queda dentro de ella.
  let host = null, pop = null, opener = null, scroller = null;
  const closePop = (refocus) => {
    if (pop) pop.remove();
    pop = null;
    if (scroller) scroller.removeEventListener("scroll", onScroll);
    scroller = null;
    if (refocus && opener) opener.focus();
    opener = null;
  };
  const onScroll = () => closePop(false);
  const onDown = (e) => { if (pop && !pop.contains(e.target)) closePop(false); };
  const onKey = (e) => { if (e.key === "Escape" && pop) closePop(true); };

  function openPop(rect, byKey) {
    if (!host) return;
    closePop(false);
    opener = rect;
    const date = rect.dataset.date, n = Number(rect.dataset.trips);
    pop = document.createElement("div");
    pop.className = "hm-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", "Detalle del día");
    const t = document.createElement("span");
    t.className = "num";
    t.textContent = rect.dataset.text;
    pop.append(t);
    let link = null;
    if (n > 0) {
      link = document.createElement("a");
      link.href = `#/trayectos/${date.slice(0, 7)}?dia=${date.slice(8)}`;
      link.textContent = "Ver trayectos ›";
      pop.append(link);
    }
    host.append(pop);
    const hr = host.getBoundingClientRect(), cr = rect.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    const cx = cr.left + cr.width / 2 - hr.left;
    pop.style.left = `${Math.round(Math.max(8, Math.min(hr.width - pw - 8, cx - pw / 2)))}px`;
    const above = cr.top - hr.top - ph - 8;
    pop.style.top = `${Math.round(above >= 4 ? above : cr.bottom - hr.top + 8)}px`;
    scroller = svg.closest(".hm-scroll");
    if (scroller) scroller.addEventListener("scroll", onScroll, { passive: true });
    if (byKey && link) link.focus({ preventScroll: true });
  }

  svg.attachPopover = (el) => {
    host = el;
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
  };
  svg.dispose = () => {
    closePop(false);
    document.removeEventListener("pointerdown", onDown);
    document.removeEventListener("keydown", onKey);
  };
  return svg;
}

export function monthBars(months, { selected, onSelect }) {
  const svg = s("svg", { class: "mb", role: "group", "aria-label": "Kilómetros por mes" });
  const H = 176, PAD_T = 20, PAD_B = 22;
  const wide = window.matchMedia("(min-width: 900px)");
  let built = -1;

  function build(w) {
    built = w;
    svg.replaceChildren();
    svg.setAttribute("viewBox", `0 0 ${w} ${H}`);
    const slot = w / months.length;
    const bw = Math.max(8, Math.min(44, slot * 0.62));
    const max = Math.max(1, ...months.map((m) => m.km));
    const base = H - PAD_B;
    svg.append(s("line", { class: "mb-base", x1: 0, x2: w, y1: base + 0.5, y2: base + 0.5 }));
    months.forEach((m, i) => {
      const x = i * slot + (slot - bw) / 2;
      const bh = m.km > 0 ? Math.max(2, (m.km / max) * (base - PAD_T)) : 1;
      const name = monthName(m.month);
      const tip = `${monthLong(m.month)} · ${n0(m.km)} km · ${plural(m.trips, "trayecto", "trayectos")} · ${dur(m.drive_ms)}`;
      const g = s("g", { class: "mb-bar" + (m.month === selected ? " sel" : ""), role: "img", "aria-label": tip, tabindex: "0" },
        title(tip),
        s("rect", { class: "mb-hit", x: i * slot, y: 0, width: slot, height: H }),
        s("rect", { class: "mb-fill", x, y: base - bh, width: bw, height: bh, rx: 3 }),
        s("text", { class: "mb-val", x: x + bw / 2, y: base - bh - 5, "text-anchor": "middle" }, m.km > 0 ? n0(m.km) : ""),
        s("text", { class: "mb-x", x: x + bw / 2, y: H - 6, "text-anchor": "middle" },
          wide.matches ? abbr(name) : name.charAt(0).toUpperCase()));
      onActivate(g, () => onSelect && onSelect(m.month));
      svg.append(g);
    });
  }

  build(336);
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => {
      const w = Math.round(svg.getBoundingClientRect().width);
      if (w > 0 && w !== built) build(w);
    });
    ro.observe(svg);
    svg.dispose = () => ro.disconnect();
  }
  return svg;
}
