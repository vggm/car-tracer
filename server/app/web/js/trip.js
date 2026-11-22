import { ApiError, getJSON } from "./api.js";
import { el, card, stat, emptyState, load } from "./ui.js";
import { onThemeChange } from "./theme.js";
import { addBasemap } from "./basemap.js";
import { dayLong, hhmm, dur, n0, n1, monthOf, TZ } from "./fmt.js";

const nil = (x) => x === null || x === undefined;
const filled = (a) => Array.isArray(a) && a.filter((v) => !nil(v)).length >= 2;
const SYNC = "trip-cursor";
const fClock = new Intl.DateTimeFormat("es-ES", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const rootPx = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
const H_MAIN = 14.7, H_COOL = 7.3; // rem

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Índice del punto cuyo ts está más cerca de t (points ordenados por ts).
function nearest(points, t) {
  let lo = 0, hi = points.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid][2] < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(points[lo - 1][2] - t) <= Math.abs(points[lo][2] - t)) lo--;
  return lo;
}

function notFound() {
  return el("section", { class: "card" },
    emptyState("Trayecto no encontrado"),
    el("div", { class: "trip-nf" }, el("a", { class: "btn", href: "#/trayectos" }, "Ver trayectos")));
}

export async function render(main, params) {
  const id = params[0];
  document.title = "Trayecto · Car Trace";
  let map = null, charts = [], ro = null, recolor = null, rebuild = null, basemap = null, offTheme = null;
  const onTheme = () => { if (recolor) recolor(); if (basemap) basemap.retheme(); if (rebuild) rebuild(); };

  const destroyCharts = () => {
    for (const u of charts) u.destroy();
    charts = [];
  };
  const cleanup = () => {
    if (ro) ro.disconnect();
    ro = null;
    if (offTheme) offTheme();
    offTheme = null;
    destroyCharts();
    if (basemap) basemap.destroy();
    basemap = null;
    if (map) map.remove();
    map = null;
  };

  const fetcher = async () => {
    try {
      return await getJSON(`/api/panel/trips/${encodeURIComponent(id)}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return { missing: true };
      throw e;
    }
  };

  await load(main, fetcher, (t) => {
    if (t.missing) {
      main.append(notFound());
      return;
    }
    offTheme = onThemeChange(onTheme);
    main.append(el("div", { class: "trip-head" },
      el("a", { class: "back", href: `#/trayectos/${monthOf(t.start_ts)}` }, "‹ Trayectos"),
      el("h1", { class: "page-title" }, dayLong(t.start_ts)),
      el("p", { class: "trip-sub num" }, `${hhmm(t.start_ts)} → ${hhmm(t.end_ts)}`)));

    const pts = t.points || [];
    let marker = null;
    if (pts.length) {
      const mapEl = el("div", { class: "trip-map", role: "img", "aria-label": "Mapa del trayecto" });
      main.append(el("div", { class: "card map-card" }, mapEl));
      map = L.map(mapEl, { zoomControl: true, attributionControl: true, maxZoom: 19 });
      const thisMap = map;
      addBasemap(thisMap, () => map === thisMap).then((b) => {
        if (map === thisMap) basemap = b; else b.destroy();
      }).catch(console.error);
      const ll = pts.map((p) => [p[0], p[1]]);
      const line = L.polyline(ll, { color: cssVar("--accent"), weight: 4, opacity: 0.95 }).addTo(map);
      const dot = (p, color) => L.circleMarker([p[0], p[1]], {
        radius: 6, color: cssVar("--bg"), weight: 2, fillColor: color, fillOpacity: 1,
      }).addTo(map);
      const start = dot(pts[0], cssVar("--ok"));
      const end = dot(pts[pts.length - 1], cssVar("--bad"));
      marker = L.circleMarker(ll[0], {
        radius: 6, color: cssVar("--bg"), weight: 3, fillColor: cssVar("--accent"), fillOpacity: 1,
      });
      map.fitBounds(line.getBounds(), { padding: [24, 24] });
      recolor = () => {
        line.setStyle({ color: cssVar("--accent") });
        start.setStyle({ fillColor: cssVar("--ok"), color: cssVar("--bg") });
        end.setStyle({ fillColor: cssVar("--bad"), color: cssVar("--bg") });
        marker.setStyle({ fillColor: cssVar("--accent"), color: cssVar("--bg") });
      };
    }

    main.append(card(null, el("div", { class: "stats trip-stats" },
      stat("Distancia", n1(t.km), "km"),
      stat("Duración", dur(t.duration_ms)),
      stat("Media", n0(t.avg_kmh), "km/h"),
      stat("Máxima", n0(t.max_kmh), "km/h"),
      stat("Ralentí", dur(t.idle_ms)),
      stat("Refrigerante inicial", n0(t.coolant_start), "°C"),
      stat("Refrigerante máx.", n0(t.coolant_max), "°C"),
      stat("rpm media", n0(t.rpm_avg)),
      stat("rpm máxima", n0(t.rpm_max)))));

    if (t.new_dtcs && t.new_dtcs.length) {
      const descs = new Map((t.new_dtcs_desc || []).map((d) => [d.code, d.desc]));
      main.append(card("Averías nuevas",
        el("ul", { class: "trip-dtcs" }, t.new_dtcs.map((c) =>
          el("li", {}, el("span", { class: "dtc-code" }, c),
            descs.get(c) ? el("span", { class: "dtc-desc" }, descs.get(c)) : null))),
        el("a", { class: "dtc-link", href: "#/averias" }, "Ver averías ›")));
    }

    const s = t.series;
    if (!s || !s.ts || s.ts.length < 2) return;
    const xs = s.ts.map((v) => v / 1000);
    const hasRpm = filled(s.rpm), hasCool = filled(s.coolant_c);
    const box = el("div", { class: "card charts" },
      el("h2", { class: "card-title" }, hasRpm ? "Velocidad y rpm" : "Velocidad"),
      el("div", { class: "chart", "data-chart": "main" }));
    let coolBox = null;
    if (hasCool) {
      coolBox = el("div", { class: "chart", "data-chart": "coolant" });
      box.append(el("h2", { class: "card-title chart-sub" }, "Refrigerante"), coolBox);
    }
    if (!t.has_obd) box.append(el("p", { class: "chart-note" }, "Sin datos del motor en este trayecto"));
    main.append(box);

    const tzDate = (ts) => uPlot.tzDate(new Date(ts * 1000), TZ);
    const cursorSync = () => ({ sync: { key: SYNC }, drag: { x: false, y: false }, points: { size: 7 } });
    const setCursor = (u) => {
      const idx = u.cursor.idx;
      if (!marker || !map) return;
      if (nil(idx) || idx < 0) {
        if (map.hasLayer(marker)) marker.remove();
        return;
      }
      const p = pts[nearest(pts, s.ts[idx])];
      marker.setLatLng([p[0], p[1]]);
      if (!map.hasLayer(marker)) marker.addTo(map);
    };
    // Tooltip flotante por gráfico: sigue al cursor sincronizado y muestra los valores exactos del índice.
    const tooltip = (rows) => ({
      hooks: {
        init: (u) => {
          const tip = el("div", { class: "ct-tip", hidden: true });
          const time = el("div", { class: "ct-time" });
          tip.append(time);
          const vals = rows.map((r) => {
            const v = el("span", { class: "ct-val" });
            tip.append(el("div", { class: "ct-row" }, el("i", { class: "ct-dot", style: `background:${r.color}` }), v));
            return v;
          });
          u.over.append(tip);
          // Táctil: arrastrar el dedo mueve el cursor (uPlot solo reacciona al ratón).
          const touch = (e) => {
            const t = e.touches[0], r = u.over.getBoundingClientRect();
            if (!t) return;
            const left = t.clientX - r.left;
            u.setCursor({ left, top: t.clientY - r.top }, true, true); // pub=true: cursor.sync lo publica a los demás gráficos
          };
          const off = () => u.setCursor({ left: -10, top: -10 }, true, true);
          u.over.addEventListener("touchstart", touch, { passive: true });
          u.over.addEventListener("touchmove", touch, { passive: true });
          u.over.addEventListener("touchend", off);
          u.over.addEventListener("touchcancel", off);
          u._tip = { tip, time, vals, rows };
        },
        setCursor: (u) => {
          const { tip, time, vals, rows: rs } = u._tip;
          const idx = u.cursor.idx, left = u.cursor.left;
          if (nil(idx) || idx < 0 || nil(left) || left < 0) { tip.hidden = true; return; }
          time.textContent = fClock.format(s.ts[idx]);
          rs.forEach((r, i) => {
            const v = r.data[idx];
            vals[i].parentNode.hidden = nil(v);
            vals[i].textContent = nil(v) ? "" : r.fmt(v);
          });
          tip.hidden = false;
          const gap = 12, w = tip.offsetWidth;
          const x = left + gap + w > u.over.clientWidth ? left - gap - w : left + gap;
          tip.style.transform = `translateX(${Math.max(0, x)}px)`;
        },
      },
    });
    const rowsMain = () => [
      { color: cssVar("--accent"), data: s.speed_kmh, fmt: (v) => `${n0(v)} km/h` },
      ...(hasRpm ? [{ color: cssVar("--muted"), data: s.rpm, fmt: (v) => `${n0(v)} rpm` }] : []),
    ];
    const rowsCool = () => [{ color: cssVar("--warn"), data: s.coolant_c, fmt: (v) => `${n0(v)} °C` }];
    const width = () => {
      const cs = getComputedStyle(box);
      return Math.max(220, Math.floor(box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)));
    };

    const build = () => {
      destroyCharts();
      const accent = cssVar("--accent"), muted = cssVar("--muted"), warn = cssVar("--warn"), line = cssVar("--line");
      const px = rootPx(), fontCss = `${Math.round(px * 0.7)}px system-ui, sans-serif`;
      const axis = (extra) => ({
        stroke: muted, font: fontCss, size: Math.round(px * 3.1),
        grid: { stroke: line, width: 1 }, ticks: { show: false }, ...extra,
      });
      const xAxis = axis({ size: Math.round(px * 1.7), space: Math.round(px * 4.2), grid: { show: false }, values: (u, vals) => vals.map((v) => hhmm(v * 1000)) });
      const base = { tzDate, legend: { show: false }, scales: { x: { time: true } }, hooks: { setCursor: [setCursor] } };

      const main1 = {
        ...base, width: width(), height: Math.round(H_MAIN * px), cursor: cursorSync(), plugins: [tooltip(rowsMain())],
        series: [{}, { label: "km/h", stroke: accent, width: 2, scale: "kmh", spanGaps: false },
          ...(hasRpm ? [{ label: "rpm", stroke: muted, width: 1.5, scale: "rpm", spanGaps: false }] : [])],
        scales: { x: { time: true }, kmh: { range: (u, lo, hi) => [0, Math.max(hi, 10)] }, rpm: { range: (u, lo, hi) => [0, Math.max(hi, 1000)] } },
        axes: [xAxis, axis({ scale: "kmh", label: "km/h", labelSize: Math.round(px), labelFont: fontCss }),
          ...(hasRpm ? [axis({ scale: "rpm", side: 1, values: (u, vals) => vals.map(n0), label: "rpm", labelSize: Math.round(px), labelFont: fontCss, grid: { show: false } })] : [])],
      };
      const data1 = [xs, s.speed_kmh, ...(hasRpm ? [s.rpm] : [])];
      const u1 = new uPlot(main1, data1, box.querySelector('[data-chart="main"]'));
      charts.push(u1);
      if (coolBox) {
        const u2 = new uPlot({
          ...base, width: width(), height: Math.round(H_COOL * px), cursor: cursorSync(), padding: [null, hasRpm ? Math.round(px * 4.1) : 8, null, null], plugins: [tooltip(rowsCool())],
          series: [{}, { label: "°C", stroke: warn, width: 2, spanGaps: false }],
          axes: [xAxis, axis({ label: "°C", labelSize: Math.round(px), labelFont: fontCss })],
        }, [xs, s.coolant_c], coolBox);
        charts.push(u2);
      }
    };

    build();
    let lastPx = rootPx();
    ro = new ResizeObserver(() => {
      const w = width(), px = rootPx();
      if (px !== lastPx) { lastPx = px; build(); return; } // cambia la base tipográfica: fuentes y alturas nuevas
      charts.forEach((u, i) => {
        const h = Math.round((i === 0 ? H_MAIN : H_COOL) * px);
        if (u.width !== w || u.height !== h) u.setSize({ width: w, height: h });
      });
    });
    ro.observe(box);
    rebuild = build;
  });

  return cleanup;
}
