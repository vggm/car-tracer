import { ApiError, getJSON, deleteJSON } from "./api.js";
import { el, card, stat, emptyState, load } from "./ui.js";
import { onThemeChange } from "./theme.js";
import { addBasemap } from "./basemap.js";
import { rangeStats } from "./selection.js";
import { segVar, arrowsAlong, LANE_PX, offsetPath, shiftPx, endBearings } from "./segmap.js";
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

// Un tramo suelto se normaliza a un viaje de un solo tramo: { top, segments, stops, series, points }.
// points = [lat, lon, ts] de todos los tramos, en orden.
function toModel(d, isJourney) {
  const segments = isJourney ? d.segments || [] : [d];
  return {
    top: d,
    segments,
    stops: isJourney ? d.stops || [] : [],
    series: d.series,
    points: segments.flatMap((sg) => sg.points || []),
  };
}

function notFound(isJourney) {
  return el("section", { class: "card" },
    emptyState(isJourney ? "Viaje no encontrado" : "Trayecto no encontrado"),
    el("div", { class: "trip-nf" }, el("a", { class: "btn", href: "#/trayectos" }, "Ver trayectos")));
}

export async function render(main, params, query) {
  const id = params[0];
  const isJourney = id.startsWith("v");
  document.title = `${isJourney ? "Viaje" : "Trayecto"} · Car Trace`;
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
      return await getJSON(`/api/panel/${isJourney ? "journeys" : "trips"}/${encodeURIComponent(id)}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return { missing: true };
      throw e;
    }
  };

  await load(main, fetcher, (data) => {
    if (data.missing) {
      main.append(notFound(isJourney));
      return;
    }
    const model = toModel(data, isJourney);
    const t = model.top;
    const { segments, stops } = model;
    const pts = model.points;
    offTheme = onThemeChange(onTheme);

    const headActions = el("div", { class: "journey-actions" });
    main.append(el("div", { class: "trip-head" },
      el("a", { class: "back", href: `#/trayectos/${monthOf(t.start_ts)}` }, "‹ Trayectos"),
      el("h1", { class: "page-title" }, dayLong(t.start_ts)),
      el("p", { class: "trip-sub num" }, `${hhmm(t.start_ts)} → ${hhmm(t.end_ts)}`),
      headActions));
    if (!isJourney && t.journey_id) {
      headActions.append(el("a", { class: "journey-link", href: `#/viaje/${encodeURIComponent(t.journey_id)}` }, "Parte de un viaje ›"));
    }
    if (isJourney) {
      headActions.append(el("button", {
        class: "btn", type: "button",
        onclick: async () => {
          if (!confirm("¿Separar este viaje en sus tramos?")) return;
          try {
            await deleteJSON(`/api/panel/journeys/${encodeURIComponent(id)}`);
            location.hash = `#/trayectos/${monthOf(t.start_ts)}`;
          } catch (e) {
            console.error(e);
            alert("No se pudo separar el viaje");
          }
        },
      }, "Separar"));
    }

    // Selección de tramo: null = todo el viaje, i = índice del tramo.
    let sel = null;
    let lines = [], casings = [], badges = [], arrows = [], ends = [], highlight = null;
    let marker = null;
    // Pinta líneas, bordes, insignias y flechas según la selección: los tramos no elegidos quedan atenuados.
    const paintLines = () => {
      lines.forEach((ln, i) => {
        const on = sel === null || sel === i;
        if (on) ln.setStyle({ color: cssVar(segVar(i, segments.length)), opacity: 0.95 });
        else ln.setStyle({ color: cssVar("--muted"), opacity: 0.25 });
        if (casings[i]) casings[i].setStyle({ color: cssVar("--bg"), opacity: on ? 0.85 : 0.2 });
        if (badges[i]) badges[i].setOpacity(on ? 1 : 0.45);
        if (ends[i]) ends[i].setStyle({ color: cssVar(segVar(i, segments.length)), fillColor: cssVar("--bg"), opacity: on ? 1 : 0.45, fillOpacity: on ? 1 : 0.45 });
        (arrows[i] || []).forEach((a) => a.setOpacity(on ? 1 : 0.25));
      });
    };
    // Encuadra el mapa: sel (o todo) cuando no hay rango; si hay rango, los puntos dentro de {t0, t1}.
    const fitTo = (ll) => {
      if (map && ll.length) map.fitBounds(L.latLngBounds(ll), { padding: [24, 24] });
    };
    // Resalta en el mapa y encuadra un rango {t0, t1} (ms); focus(null) quita el resalte y vuelve a la selección.
    const focus = (range) => {
      if (highlight) { highlight.remove(); highlight = null; }
      if (!map) return;
      if (range) {
        const inside = pts.filter((p) => p[2] >= range.t0 && p[2] <= range.t1).map((p) => [p[0], p[1]]);
        if (inside.length >= 2) {
          highlight = L.polyline(inside, { color: cssVar("--accent"), weight: 7, opacity: 0.95, interactive: false, className: "seg-focus" }).addTo(map);
          fitTo(inside);
          return;
        }
      }
      const base = sel === null ? pts : segments[sel].points || [];
      fitTo(base.map((p) => [p[0], p[1]]));
    };
    // Repinta la tarjeta de cifras. stats: model.top, un tramo o las cifras de un rango;
    // opts.journey: true cuando son las del viaje entero (muestra «Al volante» y «Duración total»).
    // opts.range: cifras de un intervalo seleccionado en la gráfica (km aproximados).
    const statsHost = el("div", { class: "stats trip-stats" });
    // Selección de un intervalo en la gráfica: título y enlace para quitarla.
    let ranged = false;
    const selTitle = el("span", { class: "sel-title" });
    const selHead = el("div", { class: "sel-head", hidden: true }, selTitle,
      el("a", { class: "sel-clear", href: "#", onclick: (e) => { e.preventDefault(); clearSelection(); } }, "Quitar selección"));
    const showStats = (o, opts = {}) => {
      if (opts.range) {
        statsHost.replaceChildren(
          stat("Distancia", `≈ ${n1(o.km)}`, "km"),
          stat("Al volante", dur(o.drive_ms)),
          ...(Math.abs(o.duration_ms - o.drive_ms) > 60000 ? [stat("Duración total", dur(o.duration_ms))] : []),
          stat("Media", n0(o.avg_kmh), "km/h"),
          stat("Máxima", nil(o.max_kmh) ? "—" : n0(o.max_kmh), nil(o.max_kmh) ? "" : "km/h"));
        return;
      }
      statsHost.replaceChildren(
        stat("Distancia", n1(o.km), "km"),
        ...(opts.journey
          ? [stat("Al volante", dur(o.drive_ms)), stat("Duración total", dur(o.duration_ms))]
          : [stat("Duración", dur(o.duration_ms))]),
        stat("Media", n0(o.avg_kmh), "km/h"),
        stat("Máxima", n0(o.max_kmh), "km/h"),
        stat("Ralentí", dur(o.idle_ms)),
        stat("Refrigerante inicial", n0(o.coolant_start), "°C"),
        stat("Refrigerante máx.", n0(o.coolant_max), "°C"),
        stat("rpm media", n0(o.rpm_avg)),
        stat("rpm máxima", n0(o.rpm_max)));
    };
    // Rango x (s) de la selección, para los gráficos: null = escala completa.
    const selRange = () => (sel === null ? null : { min: segments[sel].start_ts / 1000, max: segments[sel].end_ts / 1000 });
    const applyRange = () => {
      const r = selRange();
      const xs0 = model.series && model.series.ts;
      const full = xs0 && xs0.length ? { min: xs0[0] / 1000, max: xs0[xs0.length - 1] / 1000 } : null;
      const range = r || full;
      if (range) for (const u of charts) u.setScale("x", range);
    };

    if (pts.length) {
      const mapEl = el("div", { class: "trip-map", role: "img", "aria-label": isJourney ? "Mapa del viaje" : "Mapa del trayecto" });
      main.append(el("div", { class: "card map-card" }, mapEl));
      map = L.map(mapEl, { zoomControl: true, attributionControl: true, maxZoom: 19 });
      const thisMap = map;
      addBasemap(thisMap, () => map === thisMap).then((b) => {
        if (map === thisMap) basemap = b; else b.destroy();
      }).catch(console.error);
      const ll = pts.map((p) => [p[0], p[1]]);
      const segLL = (sg) => (sg.points || []).map((p) => [p[0], p[1]]);
      // Borde bajo cada línea para que se lea sobre cualquier mapa base; se añade antes y queda debajo.
      casings = segments.map((sg) => L.polyline(segLL(sg), {
        color: cssVar("--bg"), weight: 7, opacity: 0.85, interactive: false,
      }).addTo(map));
      lines = segments.map((sg, i) => L.polyline(segLL(sg), {
        color: cssVar(segVar(i, segments.length)), weight: 4, opacity: 0.95, className: "seg-line",
      }).addTo(map));
      const single = segments.length === 1;
      // Flechas de dirección (el giro va en un elemento interior: Leaflet usa transform en la raíz del icono).
      const arrowPos = segments.map((sg) => arrowsAlong(sg.points || [])); // {lat, lon, bearing} por tramo, para relayout
      arrows = segments.map((sg, i) => arrowPos[i].map((a) => L.marker([a.lat, a.lon], {
        icon: L.divIcon({
          className: "seg-arrow", iconSize: [18, 18], iconAnchor: [9, 9],
          html: `<div style="transform: rotate(${a.bearing}deg)"><svg viewBox="0 0 18 18" aria-hidden="true"><circle cx="9" cy="9" r="8" fill="var(${segVar(i, segments.length)})" stroke="var(--bg)" stroke-width="1.5"/><path d="M5 11.5 L9 5.5 L13 11.5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`,
        }),
        interactive: false, keyboard: false, zIndexOffset: 100,
      }).addTo(map)));
      // Insignia de salida de cada tramo, en su primer punto (o en la parada anterior si no hay puntos).
      const bearings = segments.map((sg) => endBearings(sg.points || []));
      // Posición base (sin desplazar) y rumbo de cada insignia/anillo, para relayout.
      const badgeAt = [], endAt = [];
      badges = segments.map((sg, i) => {
        const p0 = (sg.points || [])[0];
        const prev = i >= 1 ? stops[i - 1] : null;
        const at = p0 ? [p0[0], p0[1]] : (prev && !nil(prev.lat) && !nil(prev.lon) ? [prev.lat, prev.lon] : null);
        if (!at) return null;
        badgeAt[i] = { at, bearing: p0 ? bearings[i].first : null };
        const v = segVar(i, segments.length);
        const m = L.marker(at, {
          icon: L.divIcon({
            className: "seg-badge", iconSize: [24, 24], iconAnchor: [12, 12],
            html: `<span style="background: var(${v})">${single ? "▶" : i + 1}</span>`,
          }),
          keyboard: false, zIndexOffset: 500,
        }).addTo(map);
        let tip = single ? `Salida ${hhmm(sg.start_ts)}` : `Tramo ${i + 1} · salida ${hhmm(sg.start_ts)}`;
        if (i >= 1 && prev) tip += ` · parada de ${dur(prev.duration_ms)}`;
        m.bindTooltip(tip);
        return m;
      });
      // Fin de cada tramo salvo el último (ese lleva la bandera): anillo hueco en el color del tramo.
      ends = segments.map((sg, i) => {
        const pl = (sg.points || []).at(-1);
        if (!pl || i === segments.length - 1) return null;
        endAt[i] = { at: [pl[0], pl[1]], bearing: bearings[i].last };
        return L.circleMarker([pl[0], pl[1]], {
          radius: 6, color: cssVar(segVar(i, segments.length)), weight: 3, fillColor: cssVar("--bg"), fillOpacity: 1,
        }).addTo(map).bindTooltip(`Fin del tramo ${i + 1} · ${hhmm(pl[2])}`);
      });
      // Bandera de llegada en el último punto del viaje.
      const last = pts[pts.length - 1];
      const flag = `<svg width="22" height="26" viewBox="0 0 22 26" aria-hidden="true">`
        + `<rect x="2" y="2" width="15" height="11" fill="#fff" stroke="#111" stroke-width="1.5"/>`
        + `<path d="M2 2h5v3.67H2zM12 2h5v3.67h-5zM7 5.67h5v3.66H7zM2 9.33h5V13H2zM12 9.33h5V13h-5z" fill="#111"/>`
        + `<path d="M2 1v24" stroke="#111" stroke-width="2.5" stroke-linecap="round"/>`
        + `<path d="M2 1v24" stroke="#fff" stroke-width="1" stroke-linecap="round"/></svg>`;
      const flagMarker = L.marker([last[0], last[1]], {
        icon: L.divIcon({ className: "seg-end", iconSize: [22, 26], iconAnchor: [2, 25], html: flag }),
        keyboard: false, zIndexOffset: 1000,
      }).addTo(map).bindTooltip(`Llegada ${hhmm(last[2])}`);
      marker = L.circleMarker(ll[0], {
        radius: 6, color: cssVar("--bg"), weight: 3, fillColor: cssVar("--accent"), fillOpacity: 1,
      });
      fitTo(ll);
      // Cada línea va desplazada LANE_PX píxeles a la derecha de su sentido de marcha; se recalcula al cambiar el zoom.
      const flagBearing = bearings[segments.length - 1].last;
      const relayout = () => {
        if (!map) return;
        const z = map.getZoom();
        const proj = (lat, lon) => map.project(L.latLng(lat, lon), z);
        const unproj = (p) => map.unproject(L.point(p.x, p.y), z);
        const shifted = (lat, lon, bearing) => {
          const p = proj(lat, lon);
          return bearing === null || bearing === undefined ? p : shiftPx(p, bearing, LANE_PX);
        };
        segments.forEach((sg, i) => {
          const sp = sg.points || [];
          if (sp.length >= 2) {
            // Simplifica a 1 px antes de desplazar para que el ruido del GPS no genere picos.
            const simp = L.LineUtil.simplify(sp.map((q) => proj(q[0], q[1])), 1);
            const latlngs = offsetPath(simp, LANE_PX).map(unproj);
            casings[i].setLatLngs(latlngs);
            lines[i].setLatLngs(latlngs);
          }
          arrowPos[i].forEach((a, k) => arrows[i][k].setLatLng(unproj(shifted(a.lat, a.lon, a.bearing))));
          if (badges[i]) badges[i].setLatLng(unproj(shifted(badgeAt[i].at[0], badgeAt[i].at[1], badgeAt[i].bearing)));
          if (ends[i]) ends[i].setLatLng(unproj(shifted(endAt[i].at[0], endAt[i].at[1], endAt[i].bearing)));
        });
        // Bandera: si cae encima de la insignia de salida, se aparta a su derecha (la base del mástil queda en el borde).
        let fp = shifted(last[0], last[1], flagBearing);
        if (badgeAt[0]) {
          const bp = shifted(badgeAt[0].at[0], badgeAt[0].at[1], badgeAt[0].bearing);
          if (Math.hypot(fp.x - bp.x, fp.y - bp.y) < 20) fp = { x: bp.x + 13, y: bp.y };
        }
        flagMarker.setLatLng(unproj(fp));
      };
      relayout();
      map.on("zoomend", relayout); // el listener muere con map.remove() en cleanup
      recolor = () => {
        paintLines();
        if (highlight) highlight.setStyle({ color: cssVar("--accent") });
        marker.setStyle({ fillColor: cssVar("--accent"), color: cssVar("--bg") });
      };
    }

    // Chips de tramo (solo con 2 o más): «Todo» y uno por tramo. El estado vive en el hash (?tramo=i, 1-based).
    let chipEls = [];
    const clearSelection = (restore = true) => {
      const u = charts[0];
      if (u && u.select && u.select.width > 0) u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false);
      if (!ranged) return;
      ranged = false;
      selHead.hidden = true;
      if (!restore) return;
      focus(null);
      showStats(sel === null ? model.top : segments[sel], { journey: sel === null && isJourney });
    };
    // Aplica un intervalo {t0, t1} (ms): resalta y encuadra en el mapa, y muestra sus cifras aproximadas.
    const applySelection = (t0, t1) => {
      ranged = true;
      focus({ t0, t1 });
      const r = rangeStats(pts, model.series, t0, t1);
      selTitle.textContent = `Selección ${hhmm(t0)}–${hhmm(t1)}`;
      selHead.hidden = false;
      showStats({ ...r, duration_ms: t1 - t0 }, { range: true });
    };
    const select = (i) => {
      sel = i;
      chipEls.forEach((c, k) => {
        const on = k === (i === null ? 0 : i + 1);
        c.classList.toggle("on", on);
        c.setAttribute("aria-pressed", String(on));
      });
      paintLines();
      focus(null);
      clearSelection(false);
      showStats(i === null ? model.top : segments[i], { journey: i === null && isJourney });
      applyRange();
      history.replaceState(null, "", `#/viaje/${encodeURIComponent(id)}${i === null ? "" : `?tramo=${i + 1}`}`);
    };
    if (segments.length >= 2) {
      const mk = (label, i) => el("button", { class: "chip", type: "button", "aria-pressed": "false", onclick: () => select(i) },
        ...(i === null ? [] : [el("span", { class: "chip-sw", style: `background: var(${segVar(i, segments.length)})`, "aria-hidden": "true" })]), label);
      chipEls = [mk("Todo", null), ...segments.map((sg, i) =>
        mk(`Tramo ${i + 1} · ${hhmm(sg.start_ts)}–${hhmm(sg.end_ts)} · ${n1(sg.km)} km`, i))];
      main.append(el("div", { class: "seg-chips", role: "group", "aria-label": "Tramos del viaje" }, chipEls));
    }

    showStats(model.top, { journey: isJourney });
    main.append(card(null, selHead, statsHost));
    if (chipEls.length) {
      const q = parseInt(query && query.get("tramo"), 10);
      select(q >= 1 && q <= segments.length ? q - 1 : null);
    }

    if (t.new_dtcs && t.new_dtcs.length) {
      const descs = new Map((t.new_dtcs_desc || []).map((d) => [d.code, d.desc]));
      main.append(card("Averías nuevas",
        el("ul", { class: "trip-dtcs" }, t.new_dtcs.map((c) =>
          el("li", {}, el("span", { class: "dtc-code" }, c),
            descs.get(c) ? el("span", { class: "dtc-desc" }, descs.get(c)) : null))),
        el("a", { class: "dtc-link", href: "#/averias" }, "Ver averías ›")));
    }

    const s = model.series;
    if (!s || !s.ts || s.ts.length < 2) return;
    const xs = s.ts.map((v) => v / 1000);
    const hasRpm = filled(s.rpm), hasCool = filled(s.coolant_c);
    let selectMode = false;
    const selBtn = el("button", {
      class: "sel-mode", type: "button", "aria-pressed": "false",
      onclick: () => setSelectMode(!selectMode),
    }, "Seleccionar");
    const box = el("div", { class: "card charts" },
      el("div", { class: "chart-head" },
        el("h2", { class: "card-title" }, hasRpm ? "Velocidad y rpm" : "Velocidad"), selBtn),
      el("div", { class: "chart", "data-chart": "main" }));
    let coolBox = null;
    if (hasCool) {
      coolBox = el("div", { class: "chart", "data-chart": "coolant" });
      box.append(el("h2", { class: "card-title chart-sub" }, "Refrigerante"), coolBox);
    }
    if (!t.has_obd) box.append(el("p", { class: "chart-note" }, "Sin datos del motor en este trayecto"));
    main.append(box);

    const setSelectMode = (on) => {
      selectMode = on;
      selBtn.setAttribute("aria-pressed", String(on));
      box.classList.toggle("selecting", on);
    };
    // Convierte la selección de uPlot en un intervalo y lo aplica.
    const pick = (u) => {
      const { left, width } = u.select;
      if (!(width > 0)) return;
      applySelection(Math.round(u.posToVal(left, "x") * 1000), Math.round(u.posToVal(left + width, "x") * 1000));
    };
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
          let x0 = null;
          const touch = (e) => {
            const t = e.touches[0], r = u.over.getBoundingClientRect();
            if (!t) return;
            if (selectMode && u === charts[0]) { // modo «Seleccionar»: el arrastre dibuja el intervalo
              const x = Math.max(0, Math.min(u.over.clientWidth, t.clientX - r.left));
              if (e.type === "touchstart") x0 = x;
              if (x0 === null) return;
              u.setSelect({ left: Math.min(x0, x), width: Math.abs(x - x0), top: 0, height: u.over.clientHeight });
              return;
            }
            const left = t.clientX - r.left;
            u.setCursor({ left, top: t.clientY - r.top }, true, true); // pub=true: cursor.sync lo publica a los demás gráficos
          };
          const off = (e) => {
            if (selectMode && u === charts[0]) {
              if (e.type === "touchend" && x0 !== null && u.select.width > 0) pick(u);
              x0 = null;
              setSelectMode(false);
              return;
            }
            u.setCursor({ left: -10, top: -10 }, true, true);
          };
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
          let any = false;
          rs.forEach((r, i) => {
            const v = r.data[idx];
            vals[i].parentNode.hidden = nil(v);
            vals[i].textContent = nil(v) ? "" : r.fmt(v);
            if (!nil(v)) any = true;
          });
          if (!any) { tip.hidden = true; return; } // hueco de una parada: sin valores
          tip.hidden = false;
          const gap = 12, w = tip.offsetWidth;
          const x = left + gap + w > u.over.clientWidth ? left - gap - w : left + gap;
          tip.style.transform = `translateX(${Math.max(0, x)}px)`;
        },
      },
    });
    // Franjas de parada: rellenan [start_ts, end_ts] con --line al 50 % detrás de las series (drawClear).
    const stopBands = {
      hooks: {
        drawClear: (u) => {
          if (!stops.length) return;
          const { ctx, bbox } = u;
          ctx.save();
          ctx.globalAlpha = 0.5;
          ctx.fillStyle = cssVar("--line");
          for (const st of stops) {
            const x0 = Math.max(bbox.left, u.valToPos(st.start_ts / 1000, "x", true));
            const x1 = Math.min(bbox.left + bbox.width, u.valToPos(st.end_ts / 1000, "x", true));
            if (x1 > x0) ctx.fillRect(x0, bbox.top, x1 - x0, bbox.height);
          }
          ctx.restore();
        },
      },
    };
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
      const base = { tzDate, legend: { show: false }, scales: { x: { time: true } }, hooks: { setCursor: [setCursor], drawClear: [stopBands.hooks.drawClear] } };

      const main1 = {
        ...base, width: width(), height: Math.round(H_MAIN * px), cursor: { ...cursorSync(), drag: { x: true, y: false, setScale: false } }, plugins: [tooltip(rowsMain())],
        hooks: { ...base.hooks, setSelect: [(u) => { if (!selectMode && u.select.width > 0) pick(u); }] },
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
      applyRange();
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
