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

async function loadBadge() {
  const badge = document.getElementById("alerts-badge");
  try {
    const data = await getJSON("/api/panel/alerts");
    const since = Date.now() - 7 * 86400000;
    const n = (data.alerts || []).filter((a) => a.ts >= since).length;
    if (n > 0) {
      badge.textContent = String(n);
      badge.hidden = false;
    }
  } catch (e) {
    /* sin contador si falla */
  }
}

document.addEventListener("route", (e) => markActive(e.detail.path));
start(routes);
loadBadge();
