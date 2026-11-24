import { getJSON } from "./api.js";
import { el, card, emptyState, load } from "./ui.js";
import { dateShort } from "./fmt.js";
import { groupDtc } from "./dtcgroups.js";

const codeRows = (list) =>
  el("ul", { class: "dtc-list" }, list.map((c) =>
    el("li", {},
      el("span", { class: "dtc-line" },
        el("span", { class: "dtc-code" }, c.code),
        c.recurring ? el("span", { class: "tag bad" }, "Sigue fallando") : null),
      el("span", { class: "dtc-desc" }, c.desc))));

const group = (tone, title, count, explain, list) =>
  el("section", { class: "dtc-group" },
    el("div", { class: "dtc-head" }, el("span", { class: `dot ${tone}` }), el("strong", {}, `${title} (${count})`)),
    el("p", { class: "dtc-explain" }, explain),
    codeRows(list));

function statusCard(current) {
  if (!current) return card("Estado", emptyState("Todavía no se han leído las averías"));
  const { confirmed, watching } = groupDtc(current.active, current.pending);
  const kids = [];
  if (!confirmed.length && !watching.length) {
    kids.push(el("div", { class: "dtc-head" }, el("span", { class: "dot ok" }), el("strong", {}, "Sin averías")));
  }
  if (confirmed.length) {
    kids.push(group("high", "Confirmadas", confirmed.length,
      "La centralita las ha confirmado. Pueden encender el testigo de motor y siguen guardadas hasta que se borren.", confirmed));
  }
  if (watching.length) {
    kids.push(group("warn", "En observación", watching.length,
      "Detectadas en los últimos trayectos, sin confirmar. Si se repiten pasarán a confirmadas; si no, desaparecen solas.", watching));
  }
  kids.push(el("p", { class: "dtc-note" }, `Leídas ${dateShort(current.ts)}`));
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
