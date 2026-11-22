import test from "node:test";
import assert from "node:assert/strict";
import { haversineM, rangeStats } from "../../app/web/js/selection.js";

test("haversineM: 0.01 degrees of latitude is about 1112 m", () => {
  const d = haversineM([40, -3, 0], [40.01, -3, 1000]);
  assert.ok(Math.abs(d - 1112) <= 1, `got ${d}`);
});

test("rangeStats outside the range is all zero and max null", () => {
  const points = [[40, -3, 1000], [40.01, -3, 2000]];
  const series = { ts: [1000, 2000], speed_kmh: [10, 20] };
  assert.deepEqual(rangeStats(points, series, 5000, 6000), { km: 0, drive_ms: 0, avg_kmh: 0, max_kmh: null });
});

test("rangeStats drive_ms excludes a 230 s gap", () => {
  const points = [[40, -3, 0], [40.01, -3, 10000], [40.02, -3, 240000], [40.03, -3, 250000]];
  const series = { ts: [0, 10000, 240000, 250000], speed_kmh: [30, 40, 50, 60] };
  const r = rangeStats(points, series, 0, 250000);
  assert.equal(r.drive_ms, 20000);
  assert.ok(r.km > 3.3 && r.km < 3.4);
  assert.ok(Math.abs(r.avg_kmh - r.km / (20000 / 3600000)) < 1e-9);
  assert.equal(r.max_kmh, 60);
});

test("rangeStats max_kmh ignores null", () => {
  const points = [[40, -3, 0], [40.001, -3, 1000]];
  const series = { ts: [0, 1000, 2000], speed_kmh: [null, 25, null] };
  assert.equal(rangeStats(points, series, 0, 2000).max_kmh, 25);
});
