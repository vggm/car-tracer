import { el, card, stat, monthPicker, emptyState, load } from "./ui.js";
import { getJSON } from "./api.js";
import { km, kmh, dur, monthName, thisMonth } from "./fmt.js";
import { heatmap, monthBars } from "./charts.js";

const fToday = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" });

function legend() {
  const row = el("div", { class: "hm-legend", "aria-hidden": "true" }, el("span", {}, "Menos"));
  for (let i = 0; i <= 4; i++) row.append(el("i", { class: `l${i}` }));
  row.append(el("span", {}, "Más"));
  return row;
}

export async function render(main, params) {
  const month = params[0] || thisMonth();
  document.title = "Resumen · car-trace";
  await load(main, () => getJSON(`/api/panel/overview?month=${encodeURIComponent(month)}`), (data) => {
    const [y, m] = month.split("-").map(Number);
    const endDate = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
    const t = data.totals;

    const scroller = el("div", { class: "hm-scroll" },
      heatmap(data.days, {
        endDate, today: fToday.format(new Date()),
        onDay: (d) => { location.hash = `#/trayectos/${d.slice(0, 7)}?dia=${d.slice(8)}`; },
      }));

    main.append(
      el("h1", { class: "page-title" }, "Resumen"),
      monthPicker(month, (x) => `#/resumen/${x}`),
      card(null,
        el("div", { class: "stats" },
          stat("Kilómetros", km(t.km).replace(" km", ""), "km"),
          stat("Trayectos", String(t.trips)),
          stat("Al volante", dur(t.drive_ms ?? 0)),
          stat("Velocidad máx.", kmh(t.max_kmh ?? 0).replace(" km/h", ""), "km/h")),
        t.trips ? null : emptyState(`Sin trayectos en ${monthName(month)}`)),
      el("div", { class: "grid" },
        card("Últimos 12 meses", scroller, legend()),
        card("Kilómetros por mes",
          monthBars(data.months, { selected: month, onSelect: (mo) => { location.hash = `#/resumen/${mo}`; } }))));
    for (const c of main.querySelector(".grid").children) c.classList.add("span-2");

    scroller.scrollLeft = scroller.scrollWidth;
  });
}
