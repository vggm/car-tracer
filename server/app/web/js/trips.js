import { getJSON } from "./api.js";
import { el, monthPicker, emptyState, load } from "./ui.js";
import { thisMonth, monthName, dayLong, hhmm, dur, kmh, n1, localDate } from "./fmt.js";

function row(t) {
  const meta = el("div", { class: "trip-meta" },
    el("span", { class: "num" }, `${dur(t.duration_ms)} · ${kmh(t.avg_kmh)}`),
    t.has_obd ? null : el("span", { class: "tag" }, "sin OBD"),
    t.new_dtcs && t.new_dtcs.length ? el("span", { class: "tag bad" }, "avería nueva") : null);
  return el("a", { class: "trip-row", href: `#/trayecto/${encodeURIComponent(t.id)}` },
    el("div", { class: "trip-main" },
      el("div", { class: "trip-time num" }, `${hhmm(t.start_ts)} → ${hhmm(t.end_ts)}`),
      meta),
    el("div", { class: "trip-km num" }, n1(t.km), el("small", {}, " km")),
    el("span", { class: "trip-chev", "aria-hidden": "true" }, "›"));
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

  await load(body, () => getJSON(`/api/panel/trips?month=${encodeURIComponent(month)}`), (data) => {
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
        el("div", { class: "day-list" }, list.map(row)));
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
  });
  return () => clearTimeout(timer);
}
