import { getJSON, postJSON } from "./api.js";
import { el, monthPicker, emptyState, load } from "./ui.js";
import { thisMonth, monthName, dayLong, hhmm, dur, kmh, n1, localDate } from "./fmt.js";

function row(t) {
  const journey = t.kind === "journey";
  const meta = el("div", { class: "trip-meta" },
    el("span", { class: "num" }, journey ? `${dur(t.drive_ms)} · ${kmh(t.avg_kmh)}` : `${dur(t.duration_ms)} · ${kmh(t.avg_kmh)}`),
    journey ? el("span", { class: "tag accent" }, `${t.segments.length} tramos`) : null,
    t.has_obd ? null : el("span", { class: "tag" }, "sin OBD"),
    t.new_dtcs && t.new_dtcs.length ? el("span", { class: "tag bad" }, "avería nueva") : null);
  const href = journey ? `#/viaje/${encodeURIComponent(t.id)}` : `#/trayecto/${encodeURIComponent(t.id)}`;
  return el("a", { class: "trip-row", href },
    el("div", { class: "trip-main" },
      el("div", { class: "trip-time num" }, `${hhmm(t.start_ts)} → ${hhmm(t.end_ts)}`),
      meta),
    el("div", { class: "trip-km num" }, n1(t.km), el("small", {}, " km")),
    el("span", { class: "trip-chev", "aria-hidden": "true" }, "›"));
}

// Línea de parada entre dos elementos consecutivos: newer es el más reciente, older el anterior en el tiempo.
function gapLine(newer, older, refresh) {
  const lastSeg = (it) => (it.kind === "journey" ? it.segments.at(-1).id : it.id);
  const firstSeg = (it) => (it.kind === "journey" ? it.segments[0].id : it.id);
  const link = el("a", { href: "#", class: "trip-join" }, "Unir");
  const line = el("div", { class: "trip-gap" }, `Parada de ${dur(newer.gap_before_ms)} · `, link);
  let busy = false;
  link.addEventListener("click", async (ev) => {
    ev.preventDefault();
    if (busy) return;
    busy = true;
    link.setAttribute("aria-disabled", "true");
    try {
      await postJSON("/api/panel/journeys", { trip_ids: [lastSeg(older), firstSeg(newer)] });
      refresh();
    } catch (e) {
      busy = false;
      link.removeAttribute("aria-disabled");
      line.querySelector(".trip-join-err")?.remove();
      const err = el("span", { class: "trip-join-err", role: "alert" }, " No se pudo unir");
      if (e && e.status === 422) {
        // Los trayectos cambiaron (llegaron datos nuevos): se ofrece recargar en vez de repintar solo, que borraría el aviso.
        const again = el("a", { href: "#", class: "trip-join" }, "Actualizar");
        again.addEventListener("click", (ev2) => { ev2.preventDefault(); refresh(); });
        err.append(" · ", again);
      }
      line.append(err);
    }
  });
  return line;
}

function dayList(list, refresh) {
  const out = [];
  list.forEach((t, i) => {
    out.push(row(t));
    const older = list[i + 1];
    if (older && t.gap_before_ms != null) out.push(gapLine(t, older, refresh));
  });
  return out;
}

export async function render(main, params, query) {
  const month = params[0] || thisMonth();
  document.title = "Trayectos · Car Trace";
  const dia = query && query.get("dia");
  const head = el("div", { class: "trips-head" },
    el("h1", { class: "page-title" }, "Trayectos"),
    monthPicker(month, (m) => `#/trayectos/${m}`));
  const body = el("div");
  main.append(head, body);
  let timer = null;

  const refresh = () => {
    const y = window.scrollY;
    load(body, fetchTrips, paint).then(() => body.isConnected && window.scrollTo(0, y));
  };
  const fetchTrips = () => getJSON(`/api/panel/trips?month=${encodeURIComponent(month)}`);
  const paint = (data) => {
    if (!data.trips.length) {
      body.append(emptyState(`Sin trayectos en ${monthName(month)}`));
      return;
    }
    const groups = new Map();
    for (const t of data.trips) {
      const k = localDate(t.start_ts);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(t);
    }
    for (const [k, list] of groups) {
      const total = list.reduce((s, t) => s + t.km, 0);
      const g = el("section", { class: "day-group", "data-day": k.slice(8) },
        el("div", { class: "day-head" },
          el("h2", {}, dayLong(list[0].start_ts)),
          el("span", { class: "num" }, `${n1(total)} km`)),
        el("div", { class: "day-list" }, dayList(list, refresh)));
      body.append(g);
    }
    if (dia) {
      const g = body.querySelector(`.day-group[data-day="${CSS.escape(dia.padStart(2, "0"))}"]`);
      if (g) {
        g.scrollIntoView({ block: "start" });
        g.classList.add("hl");
        timer = setTimeout(() => g.classList.remove("hl"), 1500);
      }
    }
  };
  await load(body, fetchTrips, paint);
  return () => clearTimeout(timer);
}
