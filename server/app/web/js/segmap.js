// Ayudas puras del mapa de tramos (color, rumbo y flechas). Sin DOM ni Leaflet.
import { haversineM } from "./selection.js";

const PALETTE = 6; // --seg-1 … --seg-6

// Nombre de la variable CSS del tramo i de n: acento si hay uno solo, si no la paleta (cíclica).
export function segVar(i, n) {
  return n === 1 ? "--accent" : `--seg-${(i % PALETTE) + 1}`;
}

// Rumbo inicial en grados [0, 360) de a a b ([lat, lon, ...]); 0 = norte, 90 = este.
export function bearingDeg(a, b) {
  const rad = Math.PI / 180;
  const p1 = a[0] * rad, p2 = b[0] * rad, dl = (b[1] - a[1]) * rad;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return ((Math.atan2(y, x) / rad) + 360) % 360;
}

// points: [lat, lon, ts][]. Posiciones de las flechas repartidas por distancia acumulada:
// una a mitad de recorrido si es corto (< 1500 m), tres (25/50/75 %) si no. Devuelve [{ lat, lon, bearing }].
export function arrowsAlong(points) {
  if (!points || points.length < 2) return [];
  const lens = [];
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const d = haversineM(points[i - 1], points[i]);
    lens.push(d);
    total += d;
  }
  if (total === 0) return [];
  const fracs = total < 1500 ? [0.5] : [0.25, 0.5, 0.75];
  return fracs.map((f) => {
    const target = total * f;
    let acc = 0;
    let k = 0;
    // Tramo que contiene la distancia objetivo (los de longitud 0 no pueden contenerla).
    while (k < lens.length - 1 && (lens[k] === 0 || acc + lens[k] < target)) { acc += lens[k]; k++; }
    const t = lens[k] === 0 ? 0 : Math.min(1, Math.max(0, (target - acc) / lens[k]));
    const a = points[k], b = points[k + 1];
    return { lat: a[0] + (b[0] - a[0]) * t, lon: a[1] + (b[1] - a[1]) * t, bearing: bearingDeg(a, b) };
  });
}
