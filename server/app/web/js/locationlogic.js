// Lógica pura de la vista Ubicación (sin DOM ni Leaflet, para poder probarla en node).
import { hhmm } from "./fmt.js";

const LIVE = new Set(["moving", "idle", "engine_off", "stopped"]);
const LABELS = {
  moving: "En marcha",
  idle: "Parado, motor encendido",
  engine_off: "Contacto puesto, motor apagado",
  stopped: "Parado",
  parked: "Aparcado",
  no_signal: "Sin señal",
  no_data: "Sin datos",
};

export const isLive = (state) => LIVE.has(state);
export const stateLabel = (state) => LABELS[state] ?? "";

// "hace 6 s", "hace 5 min", "hace 2 h 15 min", "hace 1 día".
export function agoText(ts, now) {
  const s = Math.max(0, Math.floor((now - ts) / 1000));
  if (s < 60) return `hace ${s} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return min % 60 ? `hace ${h} h ${min % 60} min` : `hace ${h} h`;
  const d = Math.floor(h / 24);
  return d === 1 ? "hace 1 día" : `hace ${d} días`;
}

const c6 = (x) => Number(x).toFixed(6);

export function directionsUrl(lat, lon, ua = "") {
  const la = c6(lat), lo = c6(lon);
  if (/Android/i.test(ua)) return `geo:${la},${lo}?q=${la},${lo}(Coche)`;
  return `https://www.openstreetmap.org/?mlat=${la}&mlon=${lo}#map=18/${la}/${lo}`;
}

export function subtitle(data, now) {
  const ts = data.last_ts;
  if (ts === null || ts === undefined) return "";
  if (isLive(data.state)) return `Último dato ${agoText(ts, now)}`;
  if (data.state === "parked") return `Desde las ${hhmm(ts)} · ${agoText(ts, now)}`;
  if (data.state === "no_signal") return `Desde las ${hhmm(ts)} · iba en marcha`;
  return "";
}
