import { start } from "./router.js";
import { getJSON } from "./api.js";
import * as overview from "./overview.js";
import * as trips from "./trips.js";
import * as trip from "./trip.js";
import * as dtc from "./dtc.js";
import * as alerts from "./alerts.js";

const routes = [
  { re: /^\/resumen(?:\/(\d{4}-\d{2}))?$/, view: overview },
  { re: /^\/trayectos(?:\/(\d{4}-\d{2}))?$/, view: trips },
  { re: /^\/trayecto\/([^/]+)$/, view: trip },
  { re: /^\/averias$/, view: dtc },
  { re: /^\/avisos$/, view: alerts },
];

function markActive(path) {
  const key = path.split("/")[1];
  const section = key === "trayecto" ? "trayectos" : key;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === section) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

const SEEN_KEY = "ct.alertsSeenTs";
let cache = null; // { at, alerts }

function seenTs() {
  try {
    const v = Number(localStorage.getItem(SEEN_KEY));
    return Number.isFinite(v) ? v : 0;
  } catch (e) {
    return 0;
  }
}

function paintBadge(alerts) {
  const badge = document.getElementById("alerts-badge");
  const since = Date.now() - 7 * 86400000;
  const seen = seenTs();
  const n = alerts.filter((a) => a.ts >= since && a.ts > seen).length;
  if (n > 0) {
    badge.textContent = String(n);
    badge.setAttribute("aria-label", n === 1 ? "1 aviso reciente" : `${n} avisos recientes`);
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function loadBadge() {
  try {
    if (!cache || Date.now() - cache.at >= 60000) {
      const data = await getJSON("/api/panel/alerts");
      cache = { at: Date.now(), alerts: data.alerts || [] };
    }
    paintBadge(cache.alerts);
  } catch (e) {
    /* sin contador si falla */
  }
}

document.addEventListener("route", (e) => markActive(e.detail.path));
document.addEventListener("route", loadBadge);
document.addEventListener("alerts-seen", () => {
  document.getElementById("alerts-badge").hidden = true;
});
start(routes);
