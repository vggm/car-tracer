import { getAlerts } from "./api.js";
import { el, emptyState, load } from "./ui.js";
import { rel } from "./fmt.js";

function href(a) {
  if (a.trip_id) return `#/trayecto/${encodeURIComponent(a.trip_id)}`;
  if (a.kind === "new_dtc") return "#/averias";
  return null;
}

const SEEN_KEY = "ct.alertsSeenIds";
const OLD_KEY = "ct.alertsSeenTs";
export const WEEK = 7 * 86400000;

export function readSeen() {
  try {
    localStorage.removeItem(OLD_KEY); // migración silenciosa
  } catch (e) {
    /* sin almacenamiento */
  }
  try {
    const v = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
    return new Set(Array.isArray(v) ? v : []);
  } catch (e) {
    return new Set();
  }
}

function markSeen(alerts) {
  const since = Date.now() - WEEK;
  const ids = alerts.filter((a) => a.ts >= since).map((a) => a.id);
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(ids));
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
        !prevSeen.has(a.id) && a.ts >= Date.now() - WEEK ? el("span", { class: "tag accent", style: "margin-left:.5em" }, "nuevo") : null),
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
  await load(box, () => getAlerts(), (d) => {
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
