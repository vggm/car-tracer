// Cifras aproximadas de un intervalo de un viaje. Funciones puras, sin DOM.
const R = 6371000;
const GAP_MS = 120000; // saltos mayores son paradas y no cuentan como conducción

// a, b: [lat, lon, ts]. Distancia en metros.
export function haversineM(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad, dLon = (b[1] - a[1]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

// points: [lat, lon, ts][]; series: { ts, speed_kmh }; t0, t1 en ms.
export function rangeStats(points, series, t0, t1) {
  const inside = (points || []).filter((p) => p[2] >= t0 && p[2] <= t1);
  let m = 0;
  for (let i = 1; i < inside.length; i++) m += haversineM(inside[i - 1], inside[i]);
  const km = m / 1000;
  const ts = (series && series.ts) || [], sp = (series && series.speed_kmh) || [];
  let drive_ms = 0, max_kmh = null;
  for (let i = 0; i < ts.length; i++) {
    if (ts[i] < t0 || ts[i] > t1) continue;
    const v = sp[i];
    if (v !== null && v !== undefined && (max_kmh === null || v > max_kmh)) max_kmh = v;
    if (i > 0 && ts[i - 1] >= t0) {
      const d = ts[i] - ts[i - 1];
      if (d <= GAP_MS) drive_ms += d;
    }
  }
  return { km, drive_ms, avg_kmh: drive_ms > 0 ? km / (drive_ms / 3600000) : 0, max_kmh };
}
