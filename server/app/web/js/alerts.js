import { getJSON } from "./api.js";
import { el, emptyState, load } from "./ui.js";
import { rel } from "./fmt.js";

function href(a) {
  if (a.trip_id) return `#/trayecto/${encodeURIComponent(a.trip_id)}`;
  if (a.kind === "new_dtc") return "#/averias";
  return null;
}

const SEEN_KEY = "ct.alertsSeenTs";

function readSeen() {
  try {
    const v = Number(localStorage.getItem(SEEN_KEY));
    return Number.isFinite(v) ? v : 0;
  } catch (e) {
    return 0;
  }
}

function markSeen(alerts) {
  const ts = alerts.length ? Math.max(...alerts.map((a) => a.ts)) : Date.now();
  try {
    localStorage.setItem(SEEN_KEY, String(ts));
  } catch (e) {
    /* modo privado */
  }
  document.dispatchEvent(new CustomEvent("alerts-seen"));
}

function item(a, prevSeen) {
  const link = href(a);
  const body = [
    el("span", { class: `dot ${a.severity}` }),
    el("div", { class: "alert-main" },
      el("div", { class: "alert-title" }, a.title,
        a.ts > prevSeen && a.ts >= Date.now() - 7 * 86400000 ? el("span", { class: "tag accent", style: "margin-left:.5em" }, "nuevo") : null),
      a.detail ? el("div", { class: "alert-detail" }, a.detail) : null),
    el("div", { class: "alert-ts" }, rel(a.ts)),
  ];
  return link ? el("a", { class: "card alert is-link", href: link }, body) : el("div", { class: "card alert" }, body);
}

const checkIcon = () => {
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("class", "empty-icon");
  s.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", "M5 12.5l4.5 4.5L19 7.5");
  s.append(p);
  return s;
};

export async function render(main) {
  document.title = "Avisos · Car Trace";
  main.append(el("h1", { class: "page-title" }, "Avisos"));
  const box = el("div", { class: "alert-list" });
  main.append(box);
  await load(box, () => getJSON("/api/panel/alerts"), (d) => {
    if (!d.alerts.length) {
      const e = emptyState("Todo en orden");
      e.prepend(checkIcon());
      box.append(e);
      markSeen([]);
      return;
    }
    const prevSeen = readSeen();
    box.append(...d.alerts.map((a) => item(a, prevSeen)));
    markSeen(d.alerts);
  });
}
