import { start } from "./router.js";
import { getAlerts } from "./api.js";
import * as overview from "./overview.js";
import * as trips from "./trips.js";
import * as trip from "./trip.js";
import * as dtc from "./dtc.js";
import * as alerts from "./alerts.js";
import { readSeen, WEEK } from "./alerts.js";

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

let cache = null; // { at, alerts }

function paintBadge(alerts) {
  const badge = document.getElementById("alerts-badge");
  const since = Date.now() - WEEK;
  const seen = readSeen();
  const n = alerts.filter((a) => a.ts >= since && !seen.has(a.id)).length;
  if (n > 0) {
    badge.textContent = String(n);
    badge.setAttribute("aria-label", n === 1 ? "1 aviso nuevo" : `${n} avisos nuevos`);
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function loadBadge() {
  try {
    if (!cache || Date.now() - cache.at >= 60000) {
      const data = await getAlerts();
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
