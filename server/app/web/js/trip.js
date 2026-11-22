import { ApiError, getJSON } from "./api.js";
import { el, card, stat, emptyState, load } from "./ui.js";
import { dayLong, hhmm, dur, n0, n1, monthOf, TZ } from "./fmt.js";

const nil = (x) => x === null || x === undefined;
const filled = (a) => Array.isArray(a) && a.filter((v) => !nil(v)).length >= 2;
const SYNC = "trip-cursor";

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
  document.title = "Trayecto · car-trace";
  let map = null, charts = [], ro = null, recolor = null, rebuild = null;
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onTheme = () => { if (recolor) recolor(); if (rebuild) rebuild(); };

  const destroyCharts = () => {
    for (const u of charts) u.destroy();
    charts = [];
  };
  const cleanup = () => {
    if (ro) ro.disconnect();
    ro = null;
    mq.removeEventListener("change", onTheme);
    destroyCharts();
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
    mq.addEventListener("change", onTheme);
    main.append(el("div", { class: "trip-head" },
      el("a", { class: "back", href: `#/trayectos/${monthOf(t.start_ts)}` }, "‹ Trayectos"),
      el("h1", { class: "page-title" }, dayLong(t.start_ts)),
      el("p", { class: "trip-sub num" }, `${hhmm(t.start_ts)} → ${hhmm(t.end_ts)}`)));

    const pts = t.points || [];
    let marker = null;
    if (pts.length) {
      const mapEl = el("div", { class: "trip-map", role: "img", "aria-label": "Mapa del trayecto" });
      main.append(el("div", { class: "card map-card" }, mapEl));
      map = L.map(mapEl, { zoomControl: true, attributionControl: true });
      L.tileLayer("/tiles/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
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
    const width = () => Math.max(220, Math.floor(box.clientWidth - 32));

    const build = () => {
      destroyCharts();
      const accent = cssVar("--accent"), muted = cssVar("--muted"), warn = cssVar("--warn"), line = cssVar("--line");
      const axis = (extra) => ({
        stroke: muted, font: "11px system-ui, sans-serif", size: 52,
        grid: { stroke: line, width: 1 }, ticks: { show: false }, ...extra,
      });
      const xAxis = axis({ size: 28, space: 70, grid: { show: false }, values: (u, vals) => vals.map((v) => hhmm(v * 1000)) });
      const base = { tzDate, legend: { show: false }, scales: { x: { time: true } }, hooks: { setCursor: [setCursor] } };

      const main1 = {
        ...base, width: width(), height: 220, cursor: cursorSync(),
        series: [{}, { label: "km/h", stroke: accent, width: 2, scale: "kmh", spanGaps: false },
          ...(hasRpm ? [{ label: "rpm", stroke: muted, width: 1.5, scale: "rpm", spanGaps: false }] : [])],
        scales: { x: { time: true }, kmh: { range: (u, lo, hi) => [0, Math.max(hi, 10)] }, rpm: { range: (u, lo, hi) => [0, Math.max(hi, 1000)] } },
        axes: [xAxis, axis({ scale: "kmh", label: "km/h", labelSize: 16, labelFont: "11px system-ui, sans-serif" }),
          ...(hasRpm ? [axis({ scale: "rpm", side: 1, label: "rpm", labelSize: 16, labelFont: "11px system-ui, sans-serif", grid: { show: false } })] : [])],
      };
      const data1 = [xs, s.speed_kmh, ...(hasRpm ? [s.rpm] : [])];
      const u1 = new uPlot(main1, data1, box.querySelector('[data-chart="main"]'));
      charts.push(u1);
      if (coolBox) {
        const u2 = new uPlot({
          ...base, width: width(), height: 110, cursor: cursorSync(), padding: [null, 68, null, null],
          series: [{}, { label: "°C", stroke: warn, width: 2, spanGaps: false }],
          axes: [xAxis, axis({ label: "°C", labelSize: 16, labelFont: "11px system-ui, sans-serif" })],
        }, [xs, s.coolant_c], coolBox);
        charts.push(u2);
      }
    };

    build();
    ro = new ResizeObserver(() => {
      const w = width();
      for (const u of charts) if (u.width !== w) u.setSize({ width: w, height: u.height });
    });
    ro.observe(box);
    rebuild = build;
  });

  return cleanup;
}
