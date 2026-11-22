import { getJSON } from "./api.js";
import { el, card, emptyState, load } from "./ui.js";
import { dateShort } from "./fmt.js";

const codeRows = (list) =>
  el("ul", { class: "dtc-list" }, list.map((c) =>
    el("li", {}, el("span", { class: "dtc-code" }, c.code), el("span", { class: "dtc-desc" }, c.desc))));

const same = (a, b) => a.length === b.length && a.every((c) => b.some((d) => d.code === c.code));

function statusCard(current) {
  if (!current) return card("Estado", emptyState("Todavía no se han leído las averías"));
  const { active, pending, ts } = current;
  const kids = [];
  if (!active.length && !pending.length) {
    kids.push(el("div", { class: "dtc-head" }, el("span", { class: "dot ok" }), el("strong", {}, "Sin averías guardadas")));
  } else {
    kids.push(el("div", { class: "dtc-head" }, el("strong", {}, "Averías guardadas")));
    if (active.length) kids.push(codeRows(active));
  }
  if (pending.length && same(active, pending)) {
    kids.push(el("p", { class: "dtc-note" }, "Pendientes: las mismas."));
  } else if (pending.length) {
    kids.push(el("div", { class: "dtc-head dtc-sub" }, el("strong", {}, "Pendientes")), codeRows(pending));
  }
  kids.push(el("p", { class: "dtc-note" }, `Leídas ${dateShort(ts)}`));
  return card("Estado", ...kids);
}

const TEXT = {
  appeared: ["Apareció", "Aparecieron", "bad"],
  gone: ["Desapareció", "Desaparecieron", "ok"],
};

function historyCard(history) {
  if (!history.length) return null;
  const items = history.filter((h) => h.kind === "cleared" || TEXT[h.kind]).map((h) => {
    let label, tone;
    if (h.kind === "cleared") {
      label = "Averías borradas";
      tone = "accent";
    } else {
      const [one, many, t] = TEXT[h.kind];
      label = `${h.codes.length > 1 ? many : one} ${h.codes.join(", ")}`;
      tone = t;
    }
    return el("li", { class: "tl-item" },
      el("span", { class: `tl-dot ${tone}` }),
      el("div", { class: "tl-text" }, label),
      el("div", { class: "tl-date num" }, dateShort(h.ts)));
  });
  if (!items.length) return null;
  return card("Historial", el("ol", { class: "timeline" }, items));
}

export async function render(main) {
  document.title = "Averías · Car Trace";
  main.append(el("h1", { class: "page-title" }, "Averías"));
  const box = el("div", { class: "grid" });
  main.append(box);
  await load(box, () => getJSON("/api/panel/dtc"), (d) => {
    box.append(statusCard(d.current));
    const h = historyCard(d.history);
    if (h) box.append(h);
  });
}
