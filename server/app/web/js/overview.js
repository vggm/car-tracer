import { el, card, stat, monthPicker, emptyState, load } from "./ui.js";
import { getJSON } from "./api.js";
import { km, dur, monthName, thisMonth, today } from "./fmt.js";
import { heatmap, monthBars } from "./charts.js";

function legend() {
  const row = el("div", { class: "hm-legend", "aria-hidden": "true" }, el("span", {}, "Menos"));
  for (let i = 0; i <= 4; i++) row.append(el("i", { class: `l${i}` }));
  row.append(el("span", {}, "Más"));
  return row;
}

export async function render(main, params) {
  const month = params[0] || thisMonth();
  document.title = "Resumen · Car Trace";
  let dispose;
  await load(main, () => getJSON(`/api/panel/overview?month=${encodeURIComponent(month)}`), (data) => {
    const [y, m] = month.split("-").map(Number);
    const endDate = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
    const t = data.totals;

    const scroller = el("div", { class: "hm-scroll" });
    const hm = heatmap(data.days, { endDate, today: today() });
    scroller.append(hm);
    const hmCard = card("Últimos 12 meses", scroller, legend());
    hm.attachPopover(hmCard);

    const bars = monthBars(data.months, { selected: month, onSelect: (mo) => { location.hash = `#/resumen/${mo}`; } });
    dispose = () => { bars.dispose?.(); hm.dispose(); };

    const cards = el("div", { class: "ov-cards" },
      card(null, stat("Kilómetros", km(t.km).replace(" km", ""), "km")),
      card(null, stat("Trayectos", String(t.trips))),
      card(null, stat("Al volante", dur(t.drive_ms ?? 0))));

    main.append(
      el("h1", { class: "page-title" }, "Resumen"),
      monthPicker(month, (x) => `#/resumen/${x}`),
      cards,
      hmCard,
      card("Kilómetros por mes", bars));
    if (!t.trips) cards.after(emptyState(`Sin trayectos en ${monthName(month)}`));

    scroller.scrollLeft = scroller.scrollWidth;
  });
  return () => dispose?.();
}
