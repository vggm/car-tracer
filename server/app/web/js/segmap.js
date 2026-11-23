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

// Desplazamiento lateral en píxeles de pantalla: cada línea se dibuja a la derecha de su sentido de marcha
// (se conduce por la derecha), así los recorridos de ida y vuelta por la misma vía quedan en carriles distintos.
export const LANE_PX = 3;

// pts: [{x, y}] en píxeles de pantalla (x a la derecha, y hacia abajo). Devuelve una copia desplazada d px a la
// derecha del sentido de marcha. Los vértices interiores usan inglete (limitado a miterLimit·d); los extremos,
// la normal de su único tramo. Los tramos de longitud 0 se saltan; con menos de 2 puntos o longitud total 0 se copia igual.
export function offsetPath(pts, d, miterLimit = 2) {
  const n = pts.length;
  const copy = () => pts.map((p) => ({ x: p.x, y: p.y }));
  if (n < 2) return copy();
  // Normal unitaria derecha de cada tramo (null si mide 0): para dirección (dx, dy) es (-dy, dx)/len.
  const norms = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = pts[i + 1].x - pts[i].x, dy = pts[i + 1].y - pts[i].y;
    const len = Math.hypot(dx, dy);
    norms.push(len > 0 ? { x: -dy / len, y: dx / len } : null);
  }
  if (norms.every((v) => v === null)) return copy();
  return pts.map((p, v) => {
    let a = null, b = null;
    for (let i = v - 1; i >= 0 && !a; i--) a = norms[i];
    for (let i = v; i < n - 1 && !b; i++) b = norms[i];
    if (!a) a = b;
    if (!b) b = a;
    let sx, sy;
    const mx = a.x + b.x, my = a.y + b.y;
    const ml = Math.hypot(mx, my);
    if (ml < 1e-9) {
      // Horquilla de 180°: las normales se anulan; se usa la entrante.
      sx = a.x * d; sy = a.y * d;
    } else {
      const ux = mx / ml, uy = my / ml;
      const cos = ux * a.x + uy * a.y; // cos del semiángulo
      const k = Math.min(1 / cos, miterLimit);
      sx = ux * d * k; sy = uy * d * k;
    }
    return { x: p.x + sx, y: p.y + sy };
  });
}

// p: {x, y} en píxeles; bearing: rumbo en grados (0 norte, 90 este). Mueve p d px a la derecha de ese rumbo.
export function shiftPx(p, bearing, d) {
  const b = (bearing * Math.PI) / 180;
  return { x: p.x + Math.cos(b) * d, y: p.y + Math.sin(b) * d };
}

// points: [lat, lon, ts][]. Rumbo del primer y del último par de puntos consecutivos con longitud > 0 (null si no hay).
export function endBearings(points) {
  let first = null, last = null;
  if (points && points.length >= 2) {
    const nz = (i) => points[i][0] !== points[i + 1][0] || points[i][1] !== points[i + 1][1];
    for (let i = 0; i < points.length - 1; i++) if (nz(i)) { first = bearingDeg(points[i], points[i + 1]); break; }
    for (let i = points.length - 2; i >= 0; i--) if (nz(i)) { last = bearingDeg(points[i], points[i + 1]); break; }
  }
  return { first, last };
}
