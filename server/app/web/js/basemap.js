import { isDark } from "./theme.js";

const PM_URL = "/maps/spain.pmtiles";
const PM_LIB = "/static/vendor/protomaps-leaflet/protomaps-leaflet.js";
const KEY = "ct.basemap";
const PM_ATTR = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>';

let hasFile = null;   // promesa cacheada: ¿existe el archivo .pmtiles?
let libPromise = null;

function detect() {
  if (!hasFile) hasFile = fetch(PM_URL, { method: "HEAD" }).then((r) => r.ok, () => false);
  return hasFile;
}

// Carga perezosa de protomaps-leaflet: solo cuando se construye un mapa.
function loadLib() {
  if (window.protomapsL) return Promise.resolve();
  if (!libPromise) {
    libPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = PM_LIB;
      s.onload = resolve;
      s.onerror = () => { libPromise = null; reject(new Error("protomaps-leaflet")); };
      document.head.append(s);
    });
  }
  return libPromise;
}

const readChoice = () => { try { return localStorage.getItem(KEY) === "osm" ? "osm" : "pm"; } catch { return "pm"; } };
const saveChoice = (v) => { try { localStorage.setItem(KEY, v); } catch { /* sin almacenamiento */ } };

const osmLayer = () => L.tileLayer("/tiles/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap", className: "osm-tiles" });

const pmLayer = () => protomapsL.leafletLayer({
  url: PM_URL, flavor: isDark() ? "black" : "grayscale", lang: "es", attribution: PM_ATTR, maxZoom: 19,
});

const NOOP = { destroy() {}, retheme() {} };

// Añade la capa base al mapa. `alive()` indica si el mapa sigue en pantalla.
// Devuelve { destroy, retheme }.
export async function addBasemap(map, alive) {
  let pm = null;
  const osm = osmLayer();

  let usePm = await detect();
  if (usePm) {
    try { await loadLib(); pm = pmLayer(); } catch { usePm = false; }
  }
  if (!alive()) return NOOP;

  if (!usePm) {
    osm.addTo(map);
    return { destroy() { osm.remove(); }, retheme() {} };
  }

  let choice = readChoice();
  const active = () => (choice === "pm" ? pm : osm);
  active().addTo(map);

  const Switcher = L.Control.extend({
    options: { position: "topright" },
    onAdd() {
      const box = L.DomUtil.create("div", "basemap-switch");
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", "Mapa base");
      const mk = (id, label) => {
        const b = L.DomUtil.create("button", "", box);
        b.type = "button";
        b.textContent = label;
        b.dataset.layer = id;
        b.setAttribute("aria-pressed", String(choice === id));
        L.DomEvent.on(b, "click", () => set(id));
      };
      mk("pm", "Protomaps");
      mk("osm", "OSM");
      L.DomEvent.disableClickPropagation(box);
      return box;
    },
  });
  const ctl = new Switcher().addTo(map);

  function set(next) {
    if (next === choice) return;
    active().remove();
    choice = next;
    active().addTo(map);
    saveChoice(next);
    for (const b of ctl.getContainer().querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.layer === next));
  }

  return {
    destroy() { ctl.remove(); pm.remove(); osm.remove(); },
    // Nuevo flavor al cambiar de tema, manteniendo vista y capa elegida.
    retheme() {
      const on = choice === "pm";
      if (on) pm.remove();
      pm = pmLayer();
      if (on) pm.addTo(map);
    },
  };
}
